"""Financial Extraction Agent, Evidence Verification, and Confidence Scoring node."""
from __future__ import annotations

import json
import re
from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AuditWorkflow, MetricResult
from app.services.confidence import score_candidate
from app.services.extraction_service import extract_metrics, verify_evidence
from app.services.xbrl_service import match_metric
from app.utils.catalog import METRIC_BY_KEY, METRICS
from app.workflows.common import get_facts, get_parsed, load_filing_ref, mark_done, stage_guard


def _llm_picker(deps: Deps, wid: str):
    """LLM may only choose WHICH row to read (token-efficient: ≤6 targeted candidate rows). Values come from the filing."""
    if not deps.llm.enabled:
        return None

    def pick(md, options):
        lines = [f"{i}: table {t.index} row {r.index}: {r.text[:140]}" for i, (t, r) in enumerate(options)]
        prompt = (f"Which row is the consolidated '{md.label}' for the most recent fiscal year? "
                  f"Reply with ONLY JSON {{\"choice\": <number or null>}}.\n" + "\n".join(lines))
        res = deps.llm.complete(prompt, purpose="row_selection", workflow_id=wid, max_tokens=30)
        if not res:
            return None
        m = re.search(r"\{.*\}", res.text, re.S)
        try:
            ch = json.loads(m.group(0))["choice"] if m else None
        except (ValueError, KeyError):
            return None
        if isinstance(ch, int) and 0 <= ch < len(options):
            t, r = options[ch]
            return t.index, r.index
        return None
    return pick


@stage_guard("extraction")
def extract(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        wf, filing, ref = load_filing_ref(s, wid)
        accession, period_end, cik, url = ref.accession, ref.report_date, ref.cik, ref.url
    parsed = get_parsed(deps, ref)
    facts = get_facts(deps, cik)
    cands = extract_metrics(parsed, period_end, url, llm_row_picker=_llm_picker(deps, wid))
    counts = {"matched": 0, "mismatched": 0, "missing": 0, "unable": 0}
    with session_scope() as s:
        existing = {m.metric_key for m in s.query(MetricResult).filter_by(workflow_id=wid)}
        for c in cands:
            if c.metric_key in existing:
                continue
            md = METRIC_BY_KEY[c.metric_key]
            ok, notes = verify_evidence(c, parsed) if c.found else (False, [c.missing_reason or "not found"])
            xb = None
            if c.found:
                from_ix = c.method == "inline_xbrl_table"
                xb = match_metric(facts, concepts=list(md.concepts), period_type=md.period_type, period_end=c.period_end or period_end,
                                  accession=accession, extracted_value=c.value, scale=c.scale, from_ix=from_ix,
                                  compare_abs=md.outflow, preferred_concept=c.concept if c.concept_source == "ix_tag" else None,
                                  unit=c.currency or "USD")
                xbrl_status = xb.status
            else:
                xbrl_status = "missing" if facts else "unable"
            counts[xbrl_status] = counts.get(xbrl_status, 0) + 1
            detail = dict(c.detail)
            detail["evidence_notes"] = notes
            if c.missing_reason:
                detail["missing_reason"] = c.missing_reason
            if xb:
                detail["xbrl_match"] = {"status": xb.status, "concept": xb.concept, "xbrl_value": xb.xbrl_value, "difference": xb.difference,
                                        "tolerance": xb.tolerance, "period_start": str(xb.period_start) if xb.period_start else None,
                                        "period_end": str(xb.period_end) if xb.period_end else None, "accession": xb.accession,
                                        "unit": xb.unit, "candidates": xb.candidates, "note": xb.note, "concept_changed": xb.concept_changed}
            s.add(MetricResult(
                workflow_id=wid, metric_key=c.metric_key, label=md.label, statement=md.statement, found=c.found, value=c.value,
                currency=c.currency, unit=c.unit, scale=c.scale, raw_text=c.raw_text, period_start=c.period_start,
                period_end=c.period_end or (period_end if c.found else None), period_type=c.period_type, xbrl_concept=c.concept,
                section=c.section, location=c.location, snippet=c.snippet, source_url=url if c.found else None,
                extraction_method=c.method, extraction_detail=detail, evidence_verified=ok, xbrl_status=xbrl_status))
    found = sum(1 for c in cands if c.found)
    mark_done(wid, "extraction", f"Extracted {found} of {len(cands)} metrics from the filing; evidence re-verified; XBRL cross-check ready.",
              {"found": found, "total": len(cands), "xbrl": counts})
    return {}


@stage_guard("confidence")
def confidence(deps: Deps, wid: str) -> dict:
    scores = []
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            d = m.extraction_detail or {}
            res = score_candidate(
                found=m.found, detail=d, concept_source=("ix_tag" if m.extraction_method == "inline_xbrl_table" else
                                                         "llm_assisted" if m.extraction_method == "llm_assisted_row_selection" else "label_mapping"),
                scale=m.scale, currency=m.currency, method=m.extraction_method, column_choice=d.get("column_choice"),
                period_ok=bool(m.period_end and wf.filing.report_date and m.period_end == wf.filing.report_date),
                xbrl_status=m.xbrl_status, evidence_verified=m.evidence_verified, has_snippet=bool(m.snippet),
                has_location=bool(m.location), has_url=bool(m.source_url))
            m.confidence = res["score"]
            m.confidence_signals = res
            if m.found:
                scores.append(res["score"])
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0
    mark_done(wid, "confidence", f"Confidence scored for {len(scores)} metrics (mean {avg}/100). Confidence is evidence quality, not audit approval.",
              {"mean": avg, "scored": len(scores)})
    return {}
