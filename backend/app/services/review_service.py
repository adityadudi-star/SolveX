"""Human review actions. ReviewEvent rows are append-only; the original extracted value is never overwritten."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditWorkflow, MetricResult, ReviewEvent
from app.models.entities import utcnow

STATUS_BY_ACTION = {"approve": "approved", "correct": "corrected", "reject": "rejected"}


class ReviewError(ValueError):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def apply_review(db: Session, metric_id: int, action: str, reviewer: str, notes: str | None, corrected_value: float | None) -> tuple[ReviewEvent, int]:
    """Record a review. Returns (event, remaining_pending_in_workflow)."""
    m = db.get(MetricResult, metric_id)
    if m is None:
        raise ReviewError("Metric not found", 404)
    if m.review_status not in ("pending", "optional"):
        raise ReviewError(f"Metric is '{m.review_status}'; only pending or optional items can be reviewed (history is append-only).", 409)
    wf = db.get(AuditWorkflow, m.workflow_id)
    if action in ("correct", "reject") and not (notes and notes.strip()):
        raise ReviewError("Reviewer notes are required for corrections and rejections.", 422)
    if action == "correct" and corrected_value is None:
        raise ReviewError("A corrected value is required.", 422)
    if not reviewer.strip():
        raise ReviewError("Reviewer identity is required.", 422)
    new_status = STATUS_BY_ACTION[action]
    ev = ReviewEvent(metric_id=m.id, workflow_id=m.workflow_id, action=action, reviewer=reviewer.strip(), original_value=m.value,
                     corrected_value=corrected_value if action == "correct" else None, notes=(notes or "").strip() or None,
                     previous_review_status=m.review_status, new_review_status=new_status, ts=utcnow())
    db.add(ev)
    m.review_status = new_status
    if action == "correct":
        m.final_value = corrected_value          # `value` (original) is untouched
    db.flush()
    pending = db.query(MetricResult).filter_by(workflow_id=m.workflow_id, review_status="pending").count()
    db.commit()
    _ = wf
    return ev, pending
