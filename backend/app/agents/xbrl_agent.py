"""XBRL Verification Agent: persists ground-truth comparison results and honest accuracy statistics."""
from __future__ import annotations

from datetime import date

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AuditWorkflow, GroundTruthResult, MetricResult
from app.workflows.common import mark_done, stage_guard

METHODOLOGY = (
    "Each extracted value is compared with SEC XBRL Company Facts for the same concept, fiscal period, unit (currency) and "
    "instant/duration type, preferring facts reported under this filing's accession number. 'Matched' means the absolute difference is within "
    "the displayed rounding tolerance (0.5 × the displayed unit scale; 0.5 USD for inline-XBRL-sourced values). "
    "Match rate = matched ÷ metrics found. Metrics with no XBRL fact are 'missing'; ambiguous cases are 'unable to match reliably'. "
    "No accuracy percentage is claimed beyond these counts."
)


def _d(s):
    return date.fromisoformat(s) if s else None


@stage_guard("xbrl_verification")
def verify(deps: Deps, wid: str) -> dict:
    counts = {"matched": 0, "mismatched": 0, "missing": 0, "unable": 0}
    with session_scope() as s:
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            x = (m.extraction_detail or {}).get("xbrl_match")
            if x is None:   # metric not found
                s.add(GroundTruthResult(workflow_id=wid, metric_id=m.id, status=m.xbrl_status, extracted_value=None,
                                        detail={"note": "Metric not found in filing; nothing to compare."}))
            else:
                s.add(GroundTruthResult(workflow_id=wid, metric_id=m.id, status=x["status"], xbrl_concept=x["concept"],
                                        xbrl_value=x["xbrl_value"], extracted_value=m.value, difference=x["difference"], tolerance=x["tolerance"],
                                        period_start=_d(x["period_start"]), period_end=_d(x["period_end"]), unit=x["unit"],
                                        accession=x["accession"], detail={"note": x["note"], "candidates": x["candidates"],
                                                                         "concept_changed": x["concept_changed"]}))
            counts[m.xbrl_status] = counts.get(m.xbrl_status, 0) + 1
        wf = s.get(AuditWorkflow, wid)
        total_found = s.query(MetricResult).filter_by(workflow_id=wid, found=True).count()
        wf.summary = {**(wf.summary or {}), "xbrl": {**counts, "metrics_found": total_found, "methodology": METHODOLOGY,
                                                   "match_rate_pct": round(counts["matched"] / total_found * 100, 1) if total_found else None}}
    mark_done(wid, "xbrl_verification", f"XBRL ground-truth comparison: {counts['matched']} matched, {counts['mismatched']} mismatched, "
                                        f"{counts['missing']} missing, {counts['unable']} unable.", counts)
    return {}
