"""Adaptive Threshold Engine — learns, per metric, from human reviewer feedback.

Design rules
* The per-metric threshold is the *review confidence floor*: confidence below it => HUMAN APPROVAL REQUIRED (low_confidence).
* Only items flagged **solely** because of low confidence teach the engine (an approval of an item that also had a mandatory
  anomaly says nothing about the confidence floor).
* Feedback is evaluated against the threshold that was ACTIVE when the item was flagged (`threshold_at_decision`) and only within the
  current `epoch` (epoch bumps on every change), so learning stays consistent after an adjustment, manual set or reset.
* Auto-adjustments need >= min_reviews qualifying reviews in the window, >= min_approval_rate approvals, move by `step`, respect
  min/max limits and a cooldown, and are applied with an atomic compare-and-swap on `epoch` (no duplicate/concurrent adjustments).
* Nothing is ever recomputed retroactively; every change is appended to `adaptive_adjustments`.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import AdaptiveAdjustment, AdaptiveFeedback, AdaptiveThreshold, MetricResult, ReviewEvent, Setting, ThresholdChange
from app.models.entities import utcnow
from app.services.settings_service import get_thresholds
from app.utils.catalog import DECISION_REQUIRED, METRICS

CONFIG_DEFAULTS: dict[str, float] = {
    "auto_tuning_enabled": 1.0,   # global switch (1 = on, 0 = off)
    "min_reviews": 10.0,          # qualifying reviews required in the current epoch
    "min_approval_rate": 80.0,    # % of those that must be Approve
    "step": 5.0,                  # percentage points per adjustment
    "min_threshold": 70.0,        # never tune below
    "max_threshold": 95.0,        # never tune above (manual set too)
    "window_width": 4.0,          # learn from confidence in [threshold - width, threshold)  (80 -> 76..79)
    "cooldown_minutes": 60.0,     # minimum time between automatic adjustments of one metric
}
CONFIG_BOUNDS: dict[str, tuple[float, float]] = {
    "auto_tuning_enabled": (0, 1), "min_reviews": (5, 1000), "min_approval_rate": (50, 100), "step": (1, 10),
    "min_threshold": (50, 95), "max_threshold": (60, 99), "window_width": (1, 10), "cooldown_minutes": (0, 10080),
}
_PREFIX = "adaptive_"
_tune_lock = threading.Lock()


class AdaptiveError(ValueError):
    pass


# ------------------------------------------------------------------ configuration
def get_config(db: Session) -> dict[str, float]:
    out = dict(CONFIG_DEFAULTS)
    for s in db.query(Setting).filter(Setting.key.like(_PREFIX + "%")).all():
        k = s.key[len(_PREFIX):]
        if k in out:
            out[k] = s.value
    return out


def update_config(db: Session, changes: dict[str, float], by: str, reason: str | None) -> dict[str, float]:
    cur = get_config(db)
    new = dict(cur)
    for k, v in changes.items():
        if k not in CONFIG_DEFAULTS:
            raise AdaptiveError(f"Unknown adaptive setting '{k}'.")
        lo, hi = CONFIG_BOUNDS[k]
        if not (lo <= v <= hi):
            raise AdaptiveError(f"{k} must be between {lo:g} and {hi:g}.")
        new[k] = float(v)
    if new["min_threshold"] >= new["max_threshold"]:
        raise AdaptiveError("min_threshold must be lower than max_threshold.")
    for k, v in new.items():
        if v == cur[k]:
            continue
        db.add(ThresholdChange(key=_PREFIX + k, old_value=cur[k], new_value=v, changed_by=by, reason=reason, ts=utcnow()))
        row = db.get(Setting, _PREFIX + k)
        if row:
            row.value, row.updated_at = v, utcnow()
        else:
            db.add(Setting(key=_PREFIX + k, value=v))
    db.commit()
    return get_config(db)


# ------------------------------------------------------------------ rows
def ensure_rows(db: Session) -> None:
    base = get_thresholds(db)["review_confidence"]
    have = {r.metric_key for r in db.query(AdaptiveThreshold.metric_key)}
    for m in METRICS:
        if m.key not in have:
            db.add(AdaptiveThreshold(metric_key=m.key, default_threshold=base, current_threshold=base, source="default", epoch=0))
    db.flush()


def sync_defaults(db: Session) -> None:
    """When the global review floor is edited in Settings, untouched metrics follow it; tuned/pinned metrics keep their own value."""
    ensure_rows(db)
    base = get_thresholds(db)["review_confidence"]
    for r in db.query(AdaptiveThreshold):
        r.default_threshold = base
        if r.source == "default":
            r.current_threshold = base
    db.flush()


def effective_threshold(db: Session, metric_key: str) -> tuple[float, str, int]:
    """(threshold, source, epoch) the decision engine must use for this metric right now."""
    ensure_rows(db)
    r = db.get(AdaptiveThreshold, metric_key)
    if r is None:                                   # unknown metric key: fall back to the global floor
        return get_thresholds(db)["review_confidence"], "default", 0
    return r.current_threshold, r.source, r.epoch


# ------------------------------------------------------------------ learning
def _eligibility(m: MetricResult) -> tuple[bool, float | None, int | None, str | None]:
    ex = m.explanation or {}
    ta = ex.get("threshold_applied")
    if not ta:
        return False, None, None, "decided before the Adaptive Threshold Engine existed"
    if not m.found or m.confidence is None:
        return False, ta["value"], ta["epoch"], "metric not found (no confidence to learn from)"
    required = [r for r in ex.get("rules_triggered", []) if r.get("level") == DECISION_REQUIRED]
    if not any(r.get("rule") == "low_confidence" for r in required):
        return False, ta["value"], ta["epoch"], "was not flagged for low confidence"
    if any(r.get("rule") != "low_confidence" for r in required):
        return False, ta["value"], ta["epoch"], "also flagged for a non-confidence reason (anomaly / accounting / XBRL)"
    return True, ta["value"], ta["epoch"], None


def record_feedback(db: Session, m: MetricResult, ev: ReviewEvent) -> AdaptiveFeedback | None:
    """Persist every reviewer decision (one row per metric — duplicates are ignored)."""
    if db.query(AdaptiveFeedback.id).filter_by(metric_id=m.id).first():
        return None
    eligible, thr, epoch, note = _eligibility(m)
    fb = AdaptiveFeedback(metric_id=m.id, workflow_id=m.workflow_id, metric_key=m.metric_key, confidence=m.confidence,
                          threshold_at_decision=thr, epoch=epoch, action=ev.action, reviewer=ev.reviewer, eligible=eligible,
                          note=note, ts=ev.ts or utcnow())
    db.add(fb)
    db.flush()
    return fb


def window_stats(db: Session, row: AdaptiveThreshold, cfg: dict[str, float]) -> dict[str, Any]:
    t, w = row.current_threshold, cfg["window_width"]
    low = t - w
    fbs = (db.query(AdaptiveFeedback).filter(AdaptiveFeedback.metric_key == row.metric_key, AdaptiveFeedback.epoch == row.epoch,
                                             AdaptiveFeedback.eligible.is_(True), AdaptiveFeedback.threshold_at_decision == t,
                                             AdaptiveFeedback.confidence >= low, AdaptiveFeedback.confidence < t).all())
    n = len(fbs)
    ap = sum(1 for f in fbs if f.action == "approve")
    return {"low": low, "high": t, "reviews": n, "approvals": ap, "rate": round(ap / n * 100, 1) if n else None,
            "needed_reviews": int(cfg["min_reviews"]), "needed_rate": cfg["min_approval_rate"]}


def maybe_autotune(db: Session, metric_key: str, now: datetime | None = None) -> AdaptiveAdjustment | None:
    cfg = get_config(db)
    if not cfg["auto_tuning_enabled"]:
        return None
    now = now or utcnow()
    with _tune_lock:
        ensure_rows(db)
        row = db.get(AdaptiveThreshold, metric_key)
        if row is None or row.auto_paused or row.source == "manual":
            return None
        t = row.current_threshold
        if t - cfg["step"] < cfg["min_threshold"] - 1e-9:
            return None
        if row.last_adjusted_at and now - row.last_adjusted_at < timedelta(minutes=cfg["cooldown_minutes"]):
            return None
        st = window_stats(db, row, cfg)
        if st["reviews"] < cfg["min_reviews"] or st["rate"] is None or st["rate"] < cfg["min_approval_rate"]:
            return None
        new = max(t - cfg["step"], cfg["min_threshold"])
        res = db.execute(update(AdaptiveThreshold).where(AdaptiveThreshold.metric_key == metric_key, AdaptiveThreshold.epoch == row.epoch)
                         .values(previous_threshold=t, current_threshold=new, source="auto", epoch=row.epoch + 1,
                                 adjustments_count=row.adjustments_count + 1, last_adjusted_at=now, last_adjustment_kind="auto", updated_at=now))
        if res.rowcount != 1:       # another worker already changed this metric — never adjust twice
            return None
        label = next(m.label for m in METRICS if m.key == metric_key)
        adj = AdaptiveAdjustment(
            metric_key=metric_key, kind="auto", previous_threshold=t, new_threshold=new,
            reason=(f"Your reviewers consistently approved {label} items between {st['low']:g}% and {t - 1:g}%. "
                    f"The threshold was automatically adjusted from {t:g}% to {new:g}%."),
            reviews_considered=st["reviews"], approvals=st["approvals"], approval_rate=st["rate"], window_low=st["low"], window_high=t,
            changed_by="Adaptive Threshold Engine", ts=now)
        db.add(adj)
        db.flush()
        db.expire(row)
        return adj


# ------------------------------------------------------------------ administration
def _set(db: Session, key: str, new: float, kind: str, source: str, reason: str, by: str) -> AdaptiveAdjustment:
    ensure_rows(db)
    with _tune_lock:
        row = db.get(AdaptiveThreshold, key)
        if row is None:
            raise AdaptiveError(f"Unknown metric '{key}'.")
        old = row.current_threshold
        now = utcnow()
        row.previous_threshold, row.current_threshold, row.source = old, new, source
        row.epoch += 1
        row.last_adjusted_at, row.last_adjustment_kind, row.updated_at = now, kind, now
        adj = AdaptiveAdjustment(metric_key=key, kind=kind, previous_threshold=old, new_threshold=new, reason=reason, changed_by=by, ts=now)
        db.add(adj)
        db.flush()
        return adj


def manual_set(db: Session, key: str, value: float, reason: str, by: str) -> AdaptiveAdjustment:
    cfg = get_config(db)
    if not (cfg["min_threshold"] <= value <= cfg["max_threshold"]):
        raise AdaptiveError(f"Threshold must be between {cfg['min_threshold']:g} and {cfg['max_threshold']:g}.")
    approval = get_thresholds(db)["approval_confidence"]
    if value >= approval:
        raise AdaptiveError("Threshold must stay below the approval confidence threshold.")
    adj = _set(db, key, value, "manual", "manual", f"Manually set by {by}: {reason}. Auto-tuning is paused for this metric until resumed.", by)
    db.commit()
    return adj


def reset(db: Session, key: str, reason: str, by: str) -> AdaptiveAdjustment:
    ensure_rows(db)
    row = db.get(AdaptiveThreshold, key)
    if row is None:
        raise AdaptiveError(f"Unknown metric '{key}'.")
    adj = _set(db, key, row.default_threshold, "reset", "default", f"Reset to the original default ({row.default_threshold:g}%) by {by}. {reason}".strip(), by)
    row.auto_paused = False
    db.commit()
    return adj


def reset_all(db: Session, reason: str, by: str) -> int:
    ensure_rows(db)
    n = 0
    for r in db.query(AdaptiveThreshold).all():
        if r.source != "default" or r.current_threshold != r.default_threshold:
            _set(db, r.metric_key, r.default_threshold, "reset", "default", f"Reset to the original default ({r.default_threshold:g}%) by {by}. {reason}".strip(), by)
            r.auto_paused = False
            n += 1
    db.commit()
    return n


def set_paused(db: Session, key: str, paused: bool, by: str) -> AdaptiveThreshold:
    ensure_rows(db)
    row = db.get(AdaptiveThreshold, key)
    if row is None:
        raise AdaptiveError(f"Unknown metric '{key}'.")
    row.auto_paused = paused
    if not paused and row.source == "manual":
        row.source = "default" if row.current_threshold == row.default_threshold else "manual"
        # resume learning from a clean slate on the (manually chosen) threshold
        row.epoch += 1
    db.commit()
    return row


# ------------------------------------------------------------------ read models
def _adj_dict(a: AdaptiveAdjustment) -> dict[str, Any]:
    return {"id": a.id, "metric_key": a.metric_key, "metric": next((m.label for m in METRICS if m.key == a.metric_key), a.metric_key),
            "kind": a.kind, "previous": a.previous_threshold, "new": a.new_threshold, "reason": a.reason,
            "reviews_considered": a.reviews_considered, "approvals": a.approvals, "approval_rate": a.approval_rate,
            "window_low": a.window_low, "window_high": a.window_high, "changed_by": a.changed_by, "ts": a.ts.isoformat()}


def history(db: Session, metric_key: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    q = db.query(AdaptiveAdjustment)
    if metric_key:
        q = q.filter_by(metric_key=metric_key)
    return [_adj_dict(a) for a in q.order_by(AdaptiveAdjustment.id.desc()).limit(limit)]


def overview(db: Session) -> dict[str, Any]:
    ensure_rows(db)
    db.commit()
    cfg = get_config(db)
    rows = {r.metric_key: r for r in db.query(AdaptiveThreshold)}
    fb_all = db.query(AdaptiveFeedback).order_by(AdaptiveFeedback.id).all()
    adjs = db.query(AdaptiveAdjustment).order_by(AdaptiveAdjustment.id.desc()).all()
    metrics, trend = [], {}
    for md in METRICS:
        r = rows[md.key]
        mine = [f for f in fb_all if f.metric_key == md.key]
        ap = sum(1 for f in mine if f.action == "approve")
        last_auto = next((a for a in adjs if a.metric_key == md.key and a.kind == "auto"), None)
        last_any = next((a for a in adjs if a.metric_key == md.key), None)
        run, pts = 0, []
        for i, f in enumerate(mine, 1):
            run += f.action == "approve"
            pts.append({"n": i, "rate": round(run / i * 100, 1), "ts": f.ts.isoformat()})
        trend[md.key] = pts[-60:]
        metrics.append({
            "metric_key": md.key, "label": md.label, "default": r.default_threshold, "current": r.current_threshold,
            "previous": r.previous_threshold, "source": r.source, "auto_paused": r.auto_paused, "epoch": r.epoch,
            "adjustments": r.adjustments_count, "last_adjusted_at": r.last_adjusted_at.isoformat() if r.last_adjusted_at else None,
            "last_adjustment_kind": r.last_adjustment_kind, "reviews_total": len(mine),
            "approval_pct_total": round(ap / len(mine) * 100, 1) if mine else None,
            "window": window_stats(db, r, cfg), "last_auto": _adj_dict(last_auto) if last_auto else None,
            "last_change": _adj_dict(last_any) if last_any else None,
        })
    run, allpts = 0, []
    for i, f in enumerate(fb_all, 1):
        run += f.action == "approve"
        allpts.append({"n": i, "rate": round(run / i * 100, 1), "ts": f.ts.isoformat()})
    trend["all"] = allpts[-60:]
    return {"config": cfg, "bounds": {k: list(v) for k, v in CONFIG_BOUNDS.items()}, "defaults": CONFIG_DEFAULTS, "metrics": metrics, "trend": trend,
            "totals": {"reviews": len(fb_all), "auto_adjustments": sum(1 for a in adjs if a.kind == "auto"), "changes": len(adjs)},
            "note": "Thresholds apply to NEW decisions only; historical decisions and records are never recomputed."}
