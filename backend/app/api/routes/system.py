from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.api.deps import Reviewer, require_reviewer
from app.api.serializers import audit_dict
from app.config import APP_NAME, APP_VERSION, DEFAULT_THRESHOLDS, THRESHOLD_BOUNDS, get_settings
from app.database.session import get_db
from app.models import AuditWorkflow, Company, Filing, MetricResult, ModelUsage, ReviewEvent, ThresholdChange
from app.schemas import HealthOut, LoginRequest, SimulateRequest, ThresholdPatch
from app.services.anomaly_service import detect
from app.services.decision_service import DecisionInput, decide
from app.services.llm import get_llm
from app.services.sec_client import get_sec_client
from app.services.settings_service import SettingsError, get_thresholds, update_thresholds
from app.utils.catalog import DECISION_LABELS, DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED, METRICS

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(live: bool = False, db: Session = Depends(get_db)):
    try:
        db.execute(text("select 1"))
        dbs = "ok"
    except Exception as e:  # noqa: BLE001
        dbs = f"error: {e}"
    llm = get_llm()
    return HealthOut(status="ok" if dbs == "ok" else "degraded", app=APP_NAME, version=APP_VERSION, database=dbs,
                     sec=get_sec_client().health(live=live),
                     llm={"provider": llm.provider, "model": llm.model or None, "enabled": llm.enabled,
                          "mode": "LLM-assisted" if llm.enabled else "Deterministic (no LLM key configured — core audit pipeline fully functional)"})


@router.post("/auth/login")
def login(body: LoginRequest):
    import hmac
    if not hmac.compare_digest(body.token, get_settings().reviewer_token):
        raise HTTPException(401, "Invalid demo reviewer token")
    return {"ok": True, "reviewer": body.reviewer.strip(),
            "warning": "Demo authentication only — a shared token, not production-grade identity or access control."}


# ----------------------------------------------------------------------------- analytics
@router.get("/analytics/summary")
def summary(db: Session = Depends(get_db)):
    wfs = db.query(AuditWorkflow)
    by_wf = {d: 0 for d in (DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED)}
    for d, n in db.query(AuditWorkflow.decision, func.count()).filter(AuditWorkflow.decision.isnot(None)).group_by(AuditWorkflow.decision):
        by_wf[d] = n
    by_metric = {d: 0 for d in by_wf}
    for d, n in db.query(MetricResult.decision, func.count()).filter(MetricResult.decision.isnot(None)).group_by(MetricResult.decision):
        by_metric[d] = n
    recent = wfs.order_by(AuditWorkflow.started_at.desc()).limit(8).all()
    return {
        "companies_audited": db.query(func.count(func.distinct(Filing.company_id))).join(AuditWorkflow, AuditWorkflow.filing_id == Filing.id).scalar() or 0,
        "filings_processed": db.query(func.count(func.distinct(AuditWorkflow.filing_id))).scalar() or 0,
        "audits_total": wfs.count(),
        "metrics_extracted": db.query(MetricResult).filter_by(found=True).count(),
        "audits_by_decision": by_wf, "metrics_by_decision": by_metric,
        "decision_labels": DECISION_LABELS,
        "pending_reviews": db.query(MetricResult).filter_by(review_status="pending").count(),
        "audits_awaiting_review": wfs.filter_by(status="awaiting_review").count(),
        "audits_failed": wfs.filter_by(status="failed").count(),
        "reviewer_actions": db.query(ReviewEvent).count(),
        "recent_audits": [audit_dict(w) for w in recent],
    }


@router.get("/analytics/trends")
def trends(cik: str = Query(...), db: Session = Depends(get_db)):
    """Multi-year series built from stored audit results (current values + stored XBRL annual history). No network calls."""
    cik = cik.zfill(10)
    comp = db.query(Company).filter_by(cik=cik).first()
    if not comp:
        raise HTTPException(404, "No stored audits for that company yet. Run an audit first.")
    thr = get_thresholds(db)
    rows = []
    for m in (db.query(MetricResult).join(AuditWorkflow).join(Filing)
              .filter(Filing.company_id == comp.id, MetricResult.found.is_(True)).order_by(MetricResult.id)):
        rows.append({"key": m.metric_key, "end": m.period_end, "value": m.value, "source": "audited", "label": m.label})
        for p in (m.extraction_detail or {}).get("history", {}).get("points", []):
            rows.append({"key": m.metric_key, "end": date.fromisoformat(p["end"]), "value": p["value"], "source": "xbrl_history", "label": m.label})
    if not rows:
        return {"company": {"cik": cik, "name": comp.name, "ticker": comp.ticker}, "series": {}, "thresholds": thr}
    df = pd.DataFrame(rows)
    df["prio"] = df["source"].map({"audited": 0, "xbrl_history": 1})
    df = df.sort_values(["key", "end", "prio"]).drop_duplicates(["key", "end"], keep="first").sort_values(["key", "end"])
    df["pct_change"] = df.groupby("key")["value"].transform(lambda s: (s.diff() / s.shift().abs()) * 100)
    df["abs_change"] = df.groupby("key")["value"].diff()
    series = {}
    for key, g in df.groupby("key"):
        pts = []
        for r in g.itertuples():
            pc = None if pd.isna(r.pct_change) else round(float(r.pct_change), 2)
            pts.append({"period_end": str(r.end), "year": r.end.year, "value": float(r.value), "source": r.source, "pct_change": pc,
                        "abs_change": None if pd.isna(r.abs_change) else float(r.abs_change),
                        "unusual": pc is not None and abs(pc) >= thr["anomaly_warning_pct"],
                        "mandatory_level": pc is not None and abs(pc) >= thr["anomaly_mandatory_pct"]})
        series[key] = {"label": g["label"].iloc[0], "points": pts}
    return {"company": {"cik": cik, "name": comp.name, "ticker": comp.ticker}, "series": series, "thresholds": thr,
            "note": "Unusual-movement markers are investigation signals, not proof of error."}


@router.get("/analytics/companies")
def audited_companies(db: Session = Depends(get_db)):
    cs = db.query(Company).join(Filing).join(AuditWorkflow).distinct().all()
    return {"companies": [{"cik": c.cik, "name": c.name, "ticker": c.ticker} for c in cs]}


# ----------------------------------------------------------------------------- settings
@router.get("/settings")
def settings(db: Session = Depends(get_db)):
    s = get_settings()
    llm = get_llm()
    changes = db.query(ThresholdChange).order_by(ThresholdChange.id.desc()).limit(50).all()
    return {
        "thresholds": get_thresholds(db), "defaults": DEFAULT_THRESHOLDS, "bounds": {k: list(v) for k, v in THRESHOLD_BOUNDS.items()},
        "notes": ["Thresholds are configurable demonstration defaults, not universal accounting standards.",
                  "Mandatory human review rules (critical accounting failure, mandatory anomaly, missing evidence, XBRL mismatch) are not configurable.",
                  "Guard rails: the approval threshold cannot be set below 95 and the mandatory anomaly threshold cannot exceed 100%."],
        "changes": [{"id": c.id, "key": c.key, "old": c.old_value, "new": c.new_value, "by": c.changed_by, "reason": c.reason, "ts": c.ts.isoformat()} for c in changes],
        "sec": get_sec_client().health(), "llm": {"provider": llm.provider, "model": llm.model or None, "enabled": llm.enabled},
        "auth": {"mode": "demo", "warning": "Demo shared-token reviewer protection; not production-grade authentication."},
        "env": {"sec_configured": s.sec_configured, "checkpoint_store": "SQLite (LangGraph SqliteSaver)", "database": s.database_url.split(":")[0]},
    }


@router.patch("/settings/thresholds")
def patch_thresholds(body: ThresholdPatch, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    changes = {k: v for k, v in body.model_dump(exclude={"reason"}).items() if v is not None}
    if not changes:
        raise HTTPException(422, "No thresholds supplied")
    try:
        return {"thresholds": update_thresholds(db, changes, reviewer.name, body.reason)}
    except SettingsError as e:
        raise HTTPException(422, str(e))


# ----------------------------------------------------------------------------- observability
@router.get("/observability/usage")
def usage(db: Session = Depends(get_db)):
    llm = get_llm()
    u = db.query(func.count(), func.coalesce(func.sum(ModelUsage.input_tokens), 0), func.coalesce(func.sum(ModelUsage.output_tokens), 0),
                 func.coalesce(func.avg(ModelUsage.latency_ms), 0), func.coalesce(func.sum(ModelUsage.retries), 0),
                 func.coalesce(func.sum(ModelUsage.cost_usd), 0)).one()
    done = db.query(AuditWorkflow).filter(AuditWorkflow.duration_ms.isnot(None)).order_by(AuditWorkflow.started_at.desc()).limit(25).all()
    sec_req = sum((w.stats or {}).get("sec_requests", 0) for w in db.query(AuditWorkflow))
    sec_retry = sum((w.stats or {}).get("sec_retries", 0) for w in db.query(AuditWorkflow))
    sec_cache = sum((w.stats or {}).get("sec_cache_hits", 0) for w in db.query(AuditWorkflow))
    return {
        "llm": {"provider": llm.provider, "model": llm.model or None, "enabled": llm.enabled, "calls": u[0], "input_tokens": int(u[1]),
                "output_tokens": int(u[2]), "avg_latency_ms": round(float(u[3]), 1), "retries": int(u[4]), "estimated_cost_usd": round(float(u[5]), 6),
                "note": "No LLM calls are made unless a provider is configured; the audit pipeline is deterministic." if not llm.enabled else ""},
        "sec": {**get_sec_client().health(), "requests": sec_req, "retries": sec_retry, "cache_hits": sec_cache},
        "workflows": [{"workflow_id": w.id, "company": w.filing.company.name, "fiscal_year": w.filing.fiscal_year, "status": w.status,
                       "wall_clock_ms": w.duration_ms, "compute_ms": (w.stats or {}).get("compute_ms"),
                       "sec_requests": (w.stats or {}).get("sec_requests", 0), "sec_retries": (w.stats or {}).get("sec_retries", 0),
                       "cache_hits": (w.stats or {}).get("sec_cache_hits", 0)} for w in done],
        "recent_model_calls": [{"ts": r.ts.isoformat(), "provider": r.provider, "model": r.model, "purpose": r.purpose, "input_tokens": r.input_tokens,
                                "output_tokens": r.output_tokens, "latency_ms": r.latency_ms, "retries": r.retries, "cost_usd": r.cost_usd, "success": r.success}
                               for r in db.query(ModelUsage).order_by(ModelUsage.id.desc()).limit(25)],
    }


# ----------------------------------------------------------------------------- decision simulator (demonstration)
@router.post("/decision/simulate")
def simulate(body: SimulateRequest, db: Session = Depends(get_db)):
    """Runs the REAL decision engine on hypothetical inputs, e.g. revenue $200M → $500M at 100/100 confidence.
    Clearly a simulation: nothing is stored and no filing is involved."""
    thr = get_thresholds(db)
    key = body.metric if body.metric in {m.key for m in METRICS} else "revenue"
    a = detect(key, body.current_value, [body.previous_value], mandatory_pct=thr["anomaly_mandatory_pct"], warning_pct=thr["anomaly_warning_pct"])
    checks = [("passed", False)] if body.accounting_checks_passed else [("failed", True)]
    d = decide(DecisionInput(found=True, confidence=body.extraction_confidence, evidence_verified=True, validation_statuses=checks,
                             anomaly_status=a.status, anomaly_mandatory=a.mandatory, xbrl_status="matched"),
               approval=thr["approval_confidence"], review=thr["review_confidence"])
    return {"simulation": True, "decision": d.decision, "decision_label": DECISION_LABELS[d.decision], "reasons": d.reasons,
            "rules_triggered": d.rules_triggered,
            "anomaly": {"pct_change": a.pct_change, "abs_change": a.abs_change, "threshold": thr["anomaly_mandatory_pct"], "status": a.status,
                        "mandatory": a.mandatory, "explanation": a.explanation},
            "inputs": body.model_dump(),
            "lesson": "A financial value can be extracted correctly and still be unsafe to approve." if d.decision == DECISION_REQUIRED and body.extraction_confidence >= 98 else None,
            "llm_involved": False}
