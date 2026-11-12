"""Anomaly Detection Agent: investigation signals only. Never alters extracted values."""
from __future__ import annotations

from app.agents.state import Deps
from app.agents.validation_agent import history_points
from app.database.session import session_scope
from app.models import AnomalyEvent, AuditWorkflow, MetricResult
from app.services.anomaly_service import detect
from app.utils.catalog import METRIC_BY_KEY
from app.workflows.common import mark_done, stage_guard


@stage_guard("anomaly")
def anomalies(deps: Deps, wid: str) -> dict:
    tally = {"normal": 0, "warning": 0, "mandatory": 0, "insufficient_history": 0}
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        thr = wf.thresholds
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            md = METRIC_BY_KEY[m.metric_key]
            cur = (abs(m.value) if md.outflow else m.value) if m.found else None
            hist = history_points(m)
            h_concept = (m.extraction_detail or {}).get("history", {}).get("concept")
            changed = bool(m.extraction_method == "inline_xbrl_table" and h_concept and m.xbrl_concept
                           and h_concept != m.xbrl_concept and h_concept.split(":")[-1] != m.xbrl_concept.split(":")[-1])
            r = detect(m.metric_key, cur, hist, mandatory_pct=thr["anomaly_mandatory_pct"], warning_pct=thr["anomaly_warning_pct"],
                       concept_changed=changed)
            s.add(AnomalyEvent(workflow_id=wid, metric_id=m.id, kind=r.kind, baseline=r.baseline, current_value=r.current,
                               previous_value=r.previous, abs_change=r.abs_change, pct_change=r.pct_change, threshold=r.threshold,
                               severity=r.severity, status=r.status, mandatory=r.mandatory, explanation=r.explanation, detail=r.detail))
            m.anomaly_status = r.status
            tally[r.status] += 1
    mark_done(wid, "anomaly", f"Anomaly investigation complete: {tally}. Anomalies are signals for review, not proof of fraud.", tally)
    return {}
