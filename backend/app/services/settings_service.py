from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import DEFAULT_THRESHOLDS, THRESHOLD_BOUNDS
from app.models import Setting, ThresholdChange
from app.models.entities import utcnow


class SettingsError(ValueError):
    pass


def get_thresholds(db: Session) -> dict[str, float]:
    out = dict(DEFAULT_THRESHOLDS)
    for s in db.query(Setting).all():
        if s.key in out:
            out[s.key] = s.value
    return out


def update_thresholds(db: Session, changes: dict[str, float], changed_by: str, reason: str | None) -> dict[str, float]:
    """Validate and apply threshold changes, recording each as an append-only ThresholdChange.

    Guard rails make it impossible to disable mandatory human review via settings.
    """
    cur = get_thresholds(db)
    new = dict(cur)
    for k, v in changes.items():
        if k not in DEFAULT_THRESHOLDS:
            raise SettingsError(f"Unknown setting '{k}'. Mandatory-review rules are not configurable.")
        lo, hi = THRESHOLD_BOUNDS[k]
        if not (lo <= v <= hi):
            raise SettingsError(f"{k} must be between {lo:g} and {hi:g} (guard rail: thresholds cannot bypass mandatory human review).")
        new[k] = float(v)
    if new["review_confidence"] >= new["approval_confidence"]:
        raise SettingsError("review_confidence must be lower than approval_confidence.")
    if new["anomaly_warning_pct"] >= new["anomaly_mandatory_pct"]:
        raise SettingsError("anomaly_warning_pct must be lower than anomaly_mandatory_pct.")
    for k, v in new.items():
        if v == cur[k]:
            continue
        db.add(ThresholdChange(key=k, old_value=cur[k], new_value=v, changed_by=changed_by, reason=reason, ts=utcnow()))
        row = db.get(Setting, k)
        if row:
            row.value, row.updated_at = v, utcnow()
        else:
            db.add(Setting(key=k, value=v))
    from app.services import adaptive_service      # untouched metrics follow the global review floor
    adaptive_service.sync_defaults(db)
    db.commit()
    return get_thresholds(db)
