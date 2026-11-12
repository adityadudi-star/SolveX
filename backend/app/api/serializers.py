from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AnomalyEvent, AuditWorkflow, MetricResult, ReviewEvent
from app.utils.catalog import DECISION_LABELS


def _d(x) -> str | None:
    return str(x) if x else None


def metric_dict(m: MetricResult, anomaly: AnomalyEvent | None = None, with_company: bool = False) -> dict[str, Any]:
    d = {
        "id": m.id, "workflow_id": m.workflow_id, "metric_key": m.metric_key, "label": m.label, "statement": m.statement,
        "found": m.found, "value": m.value, "final_value": m.final_value, "currency": m.currency, "unit": m.unit, "scale": m.scale,
        "raw_text": m.raw_text, "period_start": _d(m.period_start), "period_end": _d(m.period_end), "period_type": m.period_type,
        "xbrl_concept": m.xbrl_concept, "confidence": m.confidence, "validation_status": m.validation_status,
        "anomaly_status": m.anomaly_status, "xbrl_status": m.xbrl_status, "decision": m.decision,
        "escalation_reasons": m.escalation_reasons or [], "review_status": m.review_status, "evidence_verified": m.evidence_verified,
        "extraction_method": m.extraction_method, "section": m.section, "location": m.location, "source_url": m.source_url,
        "anomaly_pct_change": anomaly.pct_change if anomaly else None, "anomaly_severity": anomaly.severity if anomaly else None,
    }
    if with_company:
        f = m.workflow.filing
        d.update(company=f.company.name, ticker=f.company.ticker, fiscal_year=f.fiscal_year)
    return d


def audit_dict(wf: AuditWorkflow, full: bool = False) -> dict[str, Any]:
    f = wf.filing
    d = {
        "workflow_id": wf.id, "status": wf.status, "current_stage": wf.current_stage, "completed_stages": wf.completed_stages or [],
        "decision": wf.decision, "decision_label": DECISION_LABELS.get(wf.decision or ""), "error": wf.error,
        "company": {"cik": f.company.cik, "name": f.company.name, "ticker": f.company.ticker},
        "filing": {"form": f.form, "accession": f.accession, "filing_date": _d(f.filing_date), "period_end": _d(f.report_date),
                   "fiscal_year": f.fiscal_year, "url": f.url},
        "started_at": wf.started_at.isoformat(), "finished_at": wf.finished_at.isoformat() if wf.finished_at else None,
        "duration_ms": wf.duration_ms, "summary": wf.summary or {}, "stats": wf.stats or {},
    }
    if full:
        d["thresholds"] = wf.thresholds
    return d


def review_dict(r: ReviewEvent) -> dict[str, Any]:
    m = r.metric
    f = m.workflow.filing
    return {"id": r.id, "metric_id": r.metric_id, "workflow_id": r.workflow_id, "metric": m.label, "company": f.company.name,
            "fiscal_year": f.fiscal_year, "action": r.action, "reviewer": r.reviewer, "original_value": r.original_value,
            "corrected_value": r.corrected_value, "notes": r.notes, "previous_review_status": r.previous_review_status,
            "new_review_status": r.new_review_status, "ts": r.ts.isoformat()}


def anomalies_by_metric(db: Session, metric_ids: list[int]) -> dict[int, AnomalyEvent]:
    if not metric_ids:
        return {}
    return {a.metric_id: a for a in db.query(AnomalyEvent).filter(AnomalyEvent.metric_id.in_(metric_ids))}
