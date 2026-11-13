"""Decision Engine node, review preparation, Human Review interrupt gate, and post-review revalidation.

All decisions here are computed by deterministic Python (services.decision_service). No LLM involvement.
"""
from __future__ import annotations

from langgraph.types import interrupt

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AuditWorkflow, MetricResult, ReviewEvent, ValidationCheck
from app.services import adaptive_service, validation_service as v
from app.services.decision_service import DecisionInput, decide, overall_decision
from app.utils.catalog import DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED, METRIC_BY_KEY
from app.workflows.common import emit, mark_done, stage_done, stage_guard

SERIOUS_TYPES = {"unit_mismatch", "period_mismatch", "unusual_scaling"}


def effective_value(m: MetricResult) -> float | None:
    """Value after human review. The ORIGINAL (m.value) is never overwritten."""
    if m.review_status == "corrected":
        return m.final_value
    if m.review_status == "rejected":
        return None
    return m.value


@stage_guard("decision")
def decision(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        thr = wf.thresholds
        checks = s.query(ValidationCheck).filter_by(workflow_id=wid, phase="audit").all()
        decisions: list[str] = []
        by: dict[str, int] = {DECISION_PASSED: 0, DECISION_RECOMMENDED: 0, DECISION_REQUIRED: 0}
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            md = METRIC_BY_KEY[m.metric_key]
            rel = [c for c in checks if m.metric_key in (c.metric_keys or [])]
            # per-metric review floor from the Adaptive Threshold Engine (equals the global floor until a metric is tuned)
            floor, floor_src, floor_epoch = adaptive_service.effective_threshold(s, m.metric_key)
            d = decide(DecisionInput(
                found=m.found, mandatory=md.mandatory, confidence=m.confidence or 0.0, evidence_verified=m.evidence_verified,
                validation_statuses=[(c.status, c.blocking) for c in rel], anomaly_status=m.anomaly_status,
                anomaly_mandatory=m.anomaly_status == "mandatory", xbrl_status=m.xbrl_status,
                serious_unit_or_period=any(c.check_type in SERIOUS_TYPES and c.status == "failed" for c in rel)),
                approval=thr["approval_confidence"], review=floor)
            m.decision = d.decision
            m.escalation_reasons = d.reasons if d.decision != DECISION_PASSED else []
            ex = dict(m.explanation or {})
            ex["rules_triggered"] = d.rules_triggered
            ex["threshold_applied"] = {"value": floor, "source": floor_src, "epoch": floor_epoch}   # what was active at decision time
            m.explanation = ex
            decisions.append(d.decision)
            by[d.decision] += 1
        wf.decision = overall_decision(decisions)
        wf.summary = {**(wf.summary or {}), "by_decision": by, "metrics_total": len(decisions)}
    mark_done(wid, "decision", f"Audit decision: {by}. Highest-severity rule governs the overall outcome.", {"by_decision": by})
    return {}


@stage_guard("review_preparation")
def review_preparation(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        n_pending = 0
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            if m.decision == DECISION_REQUIRED:
                m.review_status, n_pending = "pending", n_pending + 1
            elif m.decision == DECISION_RECOMMENDED:
                m.review_status = "optional"
            else:
                m.review_status = "not_required"
        wf = s.get(AuditWorkflow, wid)
        wf.summary = {**(wf.summary or {}), "pending_reviews_initial": n_pending}
    mark_done(wid, "review_preparation", f"{n_pending} metric(s) queued for mandatory human review.", {"pending": n_pending})
    return {"needs_review": n_pending > 0}


def human_review(deps: Deps, wid: str) -> dict:
    """Interrupt gate. Execution is checkpointed and paused here until every mandatory review is resolved."""
    if stage_done(wid, "human_review"):
        return {}
    with session_scope() as s:
        pending = s.query(MetricResult).filter_by(workflow_id=wid, review_status="pending").count()
        wf = s.get(AuditWorkflow, wid)
        already_paused = wf.status == "awaiting_review"
        reviewed = s.query(ReviewEvent).filter_by(workflow_id=wid).count()
    if pending > 0:
        if not already_paused:
            with session_scope() as s:
                s.get(AuditWorkflow, wid).status = "awaiting_review"
            emit(wid, "human_review", "paused", f"Workflow paused at a saved checkpoint: {pending} metric(s) require human approval.",
                 {"pending": pending})
        interrupt({"workflow_id": wid, "pending": pending})
    with session_scope() as s:
        s.get(AuditWorkflow, wid).status = "running"
    mark_done(wid, "human_review", f"Human review complete ({reviewed} reviewer action(s) recorded)." if reviewed
              else "No mandatory human review was required.", {"reviewer_actions": reviewed})
    return {}


@stage_guard("post_review")
def post_review(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        ms = {m.metric_key: m for m in s.query(MetricResult).filter_by(workflow_id=wid)}
        wf = s.get(AuditWorkflow, wid)
        changed = [m for m in ms.values() if m.review_status in ("corrected", "rejected")]
        if not changed:
            msg = "No corrections or rejections; original validation results stand."
        else:
            ev = lambda k: effective_value(ms[k]) if k in ms else None  # noqa: E731
            c = v.accounting_equation(ev("total_assets"), ev("total_liabilities"), ev("shareholders_equity"),
                                      wf.thresholds["accounting_tolerance_pct"])
            c.name = "Accounting equation (after human review)"
            s.add(ValidationCheck(workflow_id=wid, check_type="post_review_" + c.check_type, name=c.name, inputs=c.inputs, formula=c.formula,
                                  result=c.result, tolerance=c.tolerance, status=c.status, blocking=c.blocking, metric_keys=c.metric_keys,
                                  explanation=c.explanation + " Uses reviewer-resolved values; originals are retained.", phase="post_review"))
            msg = f"Re-ran the accounting equation on reviewer-resolved values: {c.status}."
    mark_done(wid, "post_review", msg)
    return {}
