from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import Reviewer, require_reviewer
from app.database.session import get_db
from app.schemas import AdaptiveConfigPatch, AdaptiveManualSet, AdaptivePause, AdaptiveReason
from app.services import adaptive_service as svc

router = APIRouter(prefix="/adaptive", tags=["adaptive threshold engine"])


def _guard(fn):
    try:
        return fn()
    except svc.AdaptiveError as e:
        raise HTTPException(422, str(e))


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Per-metric thresholds, learning progress, trend data and totals (all persisted in the database)."""
    return svc.overview(db)


@router.get("/history")
def history(metric_key: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    """Append-only audit log of every threshold change: who/what changed it, why, and on how many reviews."""
    return {"history": svc.history(db, metric_key, min(limit, 500))}


@router.patch("/config")
def patch_config(body: AdaptiveConfigPatch, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    changes = {k: v for k, v in body.model_dump(exclude={"reason"}).items() if v is not None}
    if not changes:
        raise HTTPException(422, "No settings supplied")
    return {"config": _guard(lambda: svc.update_config(db, changes, reviewer.name, body.reason))}


@router.post("/reset-all")
def reset_all(body: AdaptiveReason, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    return {"reset": _guard(lambda: svc.reset_all(db, body.reason or "Bulk reset.", reviewer.name))}


@router.post("/{metric_key}/reset")
def reset(metric_key: str, body: AdaptiveReason, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    adj = _guard(lambda: svc.reset(db, metric_key, body.reason, reviewer.name))
    return {"adjustment": svc._adj_dict(adj)}


@router.post("/{metric_key}/set")
def manual_set(metric_key: str, body: AdaptiveManualSet, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    adj = _guard(lambda: svc.manual_set(db, metric_key, body.value, body.reason, reviewer.name))
    return {"adjustment": svc._adj_dict(adj)}


@router.post("/{metric_key}/auto")
def pause_resume(metric_key: str, body: AdaptivePause, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    row = _guard(lambda: svc.set_paused(db, metric_key, body.paused, reviewer.name))
    return {"metric_key": row.metric_key, "auto_paused": row.auto_paused, "source": row.source}
