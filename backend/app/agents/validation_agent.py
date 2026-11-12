"""Validation Agent: deterministic accounting checks. Every check stores inputs, formula, result, tolerance, status, explanation."""
from __future__ import annotations

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AuditWorkflow, MetricResult, ValidationCheck
from app.services import validation_service as v
from app.services.xbrl_service import annual_history
from app.utils.catalog import METRIC_BY_KEY, METRICS
from app.workflows.common import get_facts, mark_done, stage_guard

SEVERITY = {"failed": 3, "warning": 2, "passed": 1, "skipped": 0}


def history_points(m: MetricResult) -> list[float]:
    pts = (m.extraction_detail or {}).get("history", {}).get("points", [])
    vals = [p["value"] for p in pts]
    return [abs(x) for x in vals] if METRIC_BY_KEY[m.metric_key].outflow else vals


@stage_guard("validation")
def validate(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        thr = wf.thresholds
        cik, accession, fy_end = wf.filing.company.cik, wf.filing.accession, wf.filing.report_date
        facts = get_facts(deps, cik)
        ms = {m.metric_key: m for m in s.query(MetricResult).filter_by(workflow_id=wid)}
        # --- annual history from XBRL (shared with the anomaly stage)
        for key, m in ms.items():
            if not m.found or not facts:
                continue
            md = METRIC_BY_KEY[key]
            concepts = [m.xbrl_concept] if (m.extraction_method == "inline_xbrl_table" and m.xbrl_concept) else []
            concepts += list(md.concepts)
            h = annual_history(facts, concepts=list(dict.fromkeys(concepts)), period_type=md.period_type,
                               period_end=m.period_end or fy_end, accession=accession)
            d = dict(m.extraction_detail or {})
            d["history"] = {"concept": h["concept"], "restatements": h["restatements"],
                            "points": [{"end": str(p.end), "value": p.value, "accn": p.accn} for p in h["points"]]}
            m.extraction_detail = d

        checks: list[v.CheckResult] = []
        checks += v.missing_data({k: ms[k].found for k in ms})
        val = lambda k: ms[k].value if k in ms and ms[k].found else None  # noqa: E731
        checks.append(v.accounting_equation(val("total_assets"), val("total_liabilities"), val("shareholders_equity"), thr["accounting_tolerance_pct"]))
        found = {k: m for k, m in ms.items() if m.found}
        checks.append(v.period_consistency({k: (m.period_end, m.period_type) for k, m in found.items()}, fy_end))
        checks.append(v.unit_consistency({k: (m.currency, m.scale) for k, m in found.items()}))
        for k, m in found.items():
            hist = history_points(m)
            checks += v.sign_and_scale_checks(k, m.value, hist[0] if hist else None)
            if facts:
                checks.append(v.restatement_check(k, (m.extraction_detail or {}).get("history", {}).get("restatements", [])))
        checks.append(v.segment_consistency())

        for c in checks:
            single = ms.get(c.metric_keys[0]) if len(c.metric_keys) == 1 else None
            s.add(ValidationCheck(workflow_id=wid, metric_id=single.id if single else None, check_type=c.check_type, name=c.name,
                                  inputs=c.inputs, formula=c.formula, result=c.result, tolerance=c.tolerance, status=c.status,
                                  blocking=c.blocking, metric_keys=c.metric_keys, explanation=c.explanation, phase="audit"))
        for key, m in ms.items():
            rel = [c for c in checks if key in c.metric_keys]
            worst = max((c.status for c in rel), key=lambda x: SEVERITY[x], default="passed")
            m.validation_status = "passed" if worst == "skipped" else worst
    counts = {st: sum(1 for c in checks if c.status == st) for st in ("passed", "warning", "failed", "skipped")}
    mark_done(wid, "validation", f"Ran {len(checks)} deterministic checks: {counts}.", {"checks": counts})
    return {}
