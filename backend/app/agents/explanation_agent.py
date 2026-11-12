"""Explainability Agent. Separates observed facts, deterministic calculations and AI-generated narrative."""
from __future__ import annotations

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AnomalyEvent, AuditWorkflow, GroundTruthResult, MetricResult, ValidationCheck
from app.utils.catalog import DECISION_LABELS, DECISION_PASSED, DECISION_REQUIRED
from app.workflows.common import mark_done, stage_guard

OVERRIDE_NOTE = "A financial value can be extracted correctly and still be unsafe to approve."


def fmt_money(v: float | None, cur: str | None = "USD") -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    s = f"{a / 1e9:,.2f}B" if a >= 1e9 else f"{a / 1e6:,.1f}M" if a >= 1e6 else f"{a:,.0f}"
    return f"{'-' if v < 0 else ''}{'$' if (cur or 'USD') == 'USD' else (cur or '') + ' '}{s}"


def template_narrative(m: MetricResult, an: AnomalyEvent | None, xb: str) -> str:
    if not m.found:
        return (f"{m.label} could not be found in this filing and is recorded as missing (never as zero). "
                f"Decision: {DECISION_LABELS[m.decision]}. A reviewer must supply or confirm the value.")
    parts = [f"{m.label} was extracted as {fmt_money(m.value, m.currency)} for the period ending {m.period_end} "
             f"from {m.section or 'the filing'} (confidence {m.confidence:.1f}/100, XBRL: {xb})."]
    if an and an.pct_change is not None:
        parts.append(f"Versus the prior year ({fmt_money(an.previous_value, m.currency)}) it changed {an.pct_change:+.1f}%.")
    parts.append(f"Decision: {DECISION_LABELS[m.decision]}.")
    if m.escalation_reasons:
        parts.append("Why: " + " ".join(m.escalation_reasons))
    if m.decision == DECISION_REQUIRED and (m.confidence or 0) >= 98:
        parts.append(OVERRIDE_NOTE)
    return " ".join(parts)


@stage_guard("explainability")
def explain(deps: Deps, wid: str) -> dict:
    llm_used = 0
    with session_scope() as s:
        for m in s.query(MetricResult).filter_by(workflow_id=wid):
            checks = s.query(ValidationCheck).filter_by(workflow_id=wid).all()
            rel = [c for c in checks if m.metric_key in (c.metric_keys or [])]
            an = s.query(AnomalyEvent).filter_by(metric_id=m.id).first()
            gt = s.query(GroundTruthResult).filter_by(metric_id=m.id).first()
            xb = (gt.status if gt else m.xbrl_status)
            text = template_narrative(m, an, xb)
            ai = {"source": "template", "provider": None, "model": None, "text": text,
                  "note": "Deterministic template built from the recorded facts and calculations. No LLM was used."}
            if deps.llm.enabled and m.decision != DECISION_PASSED:
                res = deps.llm.complete(
                    "Rewrite the following audit finding as 2 short plain-English sentences for a reviewer. Do NOT change any number, "
                    "status or decision, and do not add new facts:\n" + text, purpose="explanation", workflow_id=wid, max_tokens=160)
                if res and res.text.strip():
                    ai = {"source": "llm", "provider": deps.llm.provider, "model": deps.llm.model, "text": res.text.strip(),
                          "note": "AI-generated paraphrase. It cannot change values or decisions; deterministic facts are shown separately.",
                          "template_text": text}
                    llm_used += 1
            d = m.extraction_detail or {}
            ex = dict(m.explanation or {})
            ex.update({
                "observed_facts": {
                    "source_url": m.source_url, "section": m.section, "location": m.location, "snippet": m.snippet, "raw_text": m.raw_text,
                    "xbrl_concept_in_filing": m.xbrl_concept, "reporting_period": {"start": str(m.period_start) if m.period_start else None,
                                                                                    "end": str(m.period_end) if m.period_end else None, "type": m.period_type},
                    "extracted_value": m.value, "currency": m.currency, "unit": m.unit, "extraction_method": m.extraction_method,
                    "evidence_verified": m.evidence_verified, "evidence_notes": d.get("evidence_notes", []),
                    "extraction_notes": d.get("notes", []),
                },
                "deterministic_calculations": {
                    "confidence": m.confidence_signals,
                    "validation_checks": [{"name": c.name, "status": c.status, "formula": c.formula, "inputs": c.inputs, "result": c.result,
                                           "tolerance": c.tolerance, "explanation": c.explanation, "blocking": c.blocking} for c in rel],
                    "historical_comparison": {"history": d.get("history", {}).get("points", []), "restatements": d.get("history", {}).get("restatements", []),
                                              "anomaly": None if not an else {"kind": an.kind, "baseline": an.baseline, "current": an.current_value,
                                                                              "previous": an.previous_value, "abs_change": an.abs_change,
                                                                              "pct_change": an.pct_change, "threshold": an.threshold, "severity": an.severity,
                                                                              "status": an.status, "mandatory": an.mandatory, "explanation": an.explanation}},
                    "xbrl_verification": d.get("xbrl_match"),
                    "decision": {"decision": m.decision, "reasons": m.escalation_reasons, "rules_triggered": ex.get("rules_triggered", [])},
                },
                "ai_explanation": ai,
            })
            m.explanation = ex
    mark_done(wid, "explainability", f"Explanations generated ({llm_used} via LLM, rest deterministic templates).", {"llm_explanations": llm_used})
    return {}
