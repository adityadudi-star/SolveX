"""Report Generation Agent: assembles the final audit report from stored, evidence-backed results."""
from __future__ import annotations

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AnomalyEvent, AuditWorkflow, MetricResult, ReviewEvent, ValidationCheck, WorkflowEvent
from app.models.entities import utcnow
from app.utils.catalog import DECISION_LABELS
from app.workflows.common import mark_done, stage_guard


def build_report(s, wid: str) -> dict:
    wf = s.get(AuditWorkflow, wid)
    f, c = wf.filing, wf.filing.company
    metrics = s.query(MetricResult).filter_by(workflow_id=wid).order_by(MetricResult.id).all()
    return {
        "product": "SolveX Financial Auditor", "tagline": "Extract the Facts. Investigate the Trust.",
        "workflow_id": wid, "generated_at": utcnow().isoformat(),
        "company": {"name": c.name, "ticker": c.ticker, "cik": c.cik},
        "filing": {"form": f.form, "accession": f.accession, "filing_date": str(f.filing_date), "period_end": str(f.report_date), "url": f.url},
        "decision": wf.decision, "decision_label": DECISION_LABELS.get(wf.decision or "", wf.decision),
        "thresholds_used": wf.thresholds, "summary": wf.summary,
        "metrics": [{"id": m.id, "key": m.metric_key, "label": m.label, "found": m.found, "value": m.value, "final_value": m.final_value,
                     "currency": m.currency, "unit": m.unit, "period_end": str(m.period_end) if m.period_end else None,
                     "confidence": m.confidence, "validation_status": m.validation_status, "anomaly_status": m.anomaly_status,
                     "xbrl_status": m.xbrl_status, "decision": m.decision, "review_status": m.review_status,
                     "escalation_reasons": m.escalation_reasons, "evidence": m.snippet, "location": m.location,
                     "narrative": (m.explanation or {}).get("ai_explanation", {}).get("text")} for m in metrics],
        "validation_checks": [{"name": k.name, "status": k.status, "formula": k.formula, "explanation": k.explanation, "phase": k.phase}
                              for k in s.query(ValidationCheck).filter_by(workflow_id=wid).order_by(ValidationCheck.id)],
        "anomalies": [{"metric_id": a.metric_id, "kind": a.kind, "status": a.status, "pct_change": a.pct_change, "threshold": a.threshold,
                       "explanation": a.explanation} for a in s.query(AnomalyEvent).filter_by(workflow_id=wid) if a.status != "normal"],
        "review_history": [{"metric_id": r.metric_id, "action": r.action, "reviewer": r.reviewer, "original_value": r.original_value,
                            "corrected_value": r.corrected_value, "notes": r.notes, "ts": r.ts.isoformat()}
                           for r in s.query(ReviewEvent).filter_by(workflow_id=wid).order_by(ReviewEvent.id)],
        "disclaimers": [
            "Confidence measures extraction evidence quality; it is not audit approval.",
            "Anomalies are investigation signals, not proof of error or fraud.",
            "Thresholds are configurable demonstration defaults, not accounting standards.",
            "SolveX is a prototype decision-support tool and does not constitute an audit opinion.",
        ],
    }


@stage_guard("report")
def report(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        pending = s.query(MetricResult).filter_by(workflow_id=wid, review_status="pending").count()
        reviews = s.query(ReviewEvent).filter_by(workflow_id=wid).all()
        wf.summary = {**(wf.summary or {}), "pending_reviews": pending,
                      "reviewed": {a: sum(1 for r in reviews if r.action == a) for a in ("approve", "correct", "reject")}}
        # active compute time = sum of (started -> completed) spans; excludes time waiting for a human
        evs = s.query(WorkflowEvent).filter_by(workflow_id=wid).order_by(WorkflowEvent.id).all()
        started: dict[str, object] = {}
        compute = 0
        for e in evs:
            if e.status == "started":
                started[e.stage] = e.ts
            elif e.status == "completed" and e.stage in started:
                compute += int((e.ts - started.pop(e.stage)).total_seconds() * 1000)
        wf.stats = {**(wf.stats or {}), "compute_ms": compute}
        wf.report = build_report(s, wid)
        wf.status = "completed"
        wf.finished_at = utcnow()
        wf.duration_ms = int((wf.finished_at - wf.started_at).total_seconds() * 1000)
    mark_done(wid, "report", "Audit report generated and stored.")
    return {}
