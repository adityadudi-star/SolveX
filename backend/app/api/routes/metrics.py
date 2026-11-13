from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import Reviewer, require_reviewer
from app.api.serializers import anomalies_by_metric, metric_dict, review_dict
from app.database.session import get_db
from app.models import AuditWorkflow, MetricResult, ReviewEvent
from app.schemas import ReviewActionBody
from app.services.review_service import ReviewError, apply_review
from app.workflows.runner import get_runner

router = APIRouter(tags=["metrics & review"])


def _m(db: Session, mid: int) -> MetricResult:
    m = db.get(MetricResult, mid)
    if m is None:
        raise HTTPException(404, "Metric not found")
    return m


@router.get("/metrics/{metric_id}")
def metric(metric_id: int, db: Session = Depends(get_db)):
    m = _m(db, metric_id)
    d = metric_dict(m, anomalies_by_metric(db, [m.id]).get(m.id), with_company=True)
    d["reviews"] = [review_dict(r) for r in m.reviews]
    return d


@router.get("/metrics/{metric_id}/evidence")
def evidence(metric_id: int, db: Session = Depends(get_db)):
    m = _m(db, metric_id)
    ex = m.explanation or {}
    calc = ex.get("deterministic_calculations", {})
    return {"metric_id": m.id, "label": m.label, "observed_facts": ex.get("observed_facts"),
            "confidence": m.confidence_signals, "validation_checks": calc.get("validation_checks", []),
            "historical_comparison": calc.get("historical_comparison"), "xbrl_verification": calc.get("xbrl_verification"),
            "decision": calc.get("decision"), "extraction_detail": m.extraction_detail,
            "original_value": m.value, "final_value": m.final_value, "review_status": m.review_status,
            "reviews": [review_dict(r) for r in m.reviews]}


@router.get("/metrics/{metric_id}/explanation")
def explanation(metric_id: int, db: Session = Depends(get_db)):
    m = _m(db, metric_id)
    ex = m.explanation or {}
    return {"metric_id": m.id, "label": m.label, "decision": m.decision, "observed_facts": ex.get("observed_facts"),
            "deterministic_calculations": ex.get("deterministic_calculations"), "ai_explanation": ex.get("ai_explanation"),
            "separation_note": "Observed facts come from the SEC filing; deterministic calculations are Python; the AI explanation (if any) is "
                               "a paraphrase that cannot alter values or decisions."}


@router.get("/reviews/pending")
def pending(db: Session = Depends(get_db)):
    ms = (db.query(MetricResult).filter_by(review_status="pending").order_by(MetricResult.created_at.desc()).all())
    an = anomalies_by_metric(db, [m.id for m in ms])
    out = []
    for m in ms:
        d = metric_dict(m, an.get(m.id), with_company=True)
        d["snippet"] = m.snippet
        d["anomaly_explanation"] = an[m.id].explanation if m.id in an else None
        out.append(d)
    return {"count": len(out), "pending": out}


@router.get("/reviews/history")
def history(workflow_id: str | None = None, metric_id: int | None = None, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(ReviewEvent)
    if workflow_id:
        q = q.filter_by(workflow_id=workflow_id)
    if metric_id:
        q = q.filter_by(metric_id=metric_id)
    return {"history": [review_dict(r) for r in q.order_by(ReviewEvent.id.desc()).limit(limit)]}


def _act(action: str, metric_id: int, body: ReviewActionBody, reviewer: Reviewer, db: Session):
    try:
        ev, pending_left = apply_review(db, metric_id, action, reviewer.name, body.notes, body.corrected_value)
    except ReviewError as e:
        raise HTTPException(e.status, str(e))
    wf = db.get(AuditWorkflow, ev.workflow_id)
    resumed = False
    if wf.status == "awaiting_review" and pending_left == 0:
        get_runner().resume_async(wf.id)
        resumed = True
    adj = getattr(ev, "adaptive_adjustment", None)
    return {"review": review_dict(ev), "pending_remaining": pending_left, "workflow_resumed": resumed,
            "adaptive": {"adjusted": None if adj is None else {"metric": adj.metric_key, "previous": adj.previous_threshold,
                                                              "new": adj.new_threshold, "reason": adj.reason}}}


@router.post("/reviews/{metric_id}/approve")
def approve(metric_id: int, body: ReviewActionBody | None = None, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    return _act("approve", metric_id, body or ReviewActionBody(), reviewer, db)


@router.post("/reviews/{metric_id}/correct")
def correct(metric_id: int, body: ReviewActionBody, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    return _act("correct", metric_id, body, reviewer, db)


@router.post("/reviews/{metric_id}/reject")
def reject(metric_id: int, body: ReviewActionBody, reviewer: Reviewer = Depends(require_reviewer), db: Session = Depends(get_db)):
    return _act("reject", metric_id, body, reviewer, db)
