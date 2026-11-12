"""Evidence-based extraction confidence. Every contributing signal is stored. No randomness.

Confidence measures how well the *extraction* is evidenced. It is NOT audit approval.
"""
from __future__ import annotations

from typing import Any

WEIGHTS = {
    "source_quality": 15,
    "parsing_certainty": 20,
    "concept_mapping": 15,
    "unit_consistency": 10,
    "period_consistency": 10,
    "xbrl_agreement": 20,
    "evidence_completeness": 10,
}
assert sum(WEIGHTS.values()) == 100


def score_candidate(*, found: bool, detail: dict[str, Any], concept_source: str | None, scale: int | None,
                    currency: str | None, method: str | None, column_choice: str | None, period_ok: bool,
                    xbrl_status: str, evidence_verified: bool, has_snippet: bool, has_location: bool,
                    has_url: bool) -> dict[str, Any]:
    if not found:
        return {"score": 0.0, "signals": {}, "weights": WEIGHTS, "note": "Metric not found; no confidence assigned."}
    sig: dict[str, dict[str, Any]] = {}

    sig["source_quality"] = {"score": 100 if has_url else 40,
                             "why": "Value read from the original SEC EDGAR filing document." if has_url else "No original filing URL."}

    certainty = detail.get("parse_certainty", 55)
    sig["parsing_certainty"] = {"score": certainty,
                                "why": {"ix_context": "Inline-XBRL fact whose context matches the reporting period.",
                                        "header_year": "Table column matched to the reporting year via header.",
                                        "positional": "Column picked by position only."}.get(column_choice or "", "Unknown column choice.")}

    cm = {"ix_tag": 100, "label_mapping": 85 if detail.get("label_priority", 9) == 0 else 72, "llm_assisted": 55}.get(concept_source or "", 40)
    sig["concept_mapping"] = {"score": cm, "why": {"ix_tag": "Concept read directly from the filing's inline XBRL tag.",
                                                    "label_mapping": "Concept inferred from the statement row label.",
                                                    "llm_assisted": "Row chosen with LLM assistance."}.get(concept_source or "", "Unknown")}

    u = 100
    why_u = "Currency and unit scale are both stated."
    if currency is None:
        u -= 30
        why_u = "Currency not stated for this value."
    if scale is None:
        u -= 40
        why_u = "Unit scale (thousands/millions) not stated." if currency else "Neither currency nor scale stated."
    sig["unit_consistency"] = {"score": max(u, 0), "why": why_u}

    sig["period_consistency"] = {"score": (100 if column_choice == "ix_context" else 90 if column_choice == "header_year" else 50) if period_ok else 20,
                                 "why": "Period matches the filing's fiscal period." if period_ok else "Period could not be reconciled with the filing."}

    x = {"matched": 100, "mismatched": 0, "missing": 50, "unable": 40}.get(xbrl_status, 40)
    sig["xbrl_agreement"] = {"score": x, "why": {"matched": "Equals the SEC XBRL Company Facts value.",
                                                 "mismatched": "Differs from the SEC XBRL Company Facts value.",
                                                 "missing": "XBRL has no comparable fact; cannot corroborate.",
                                                 "unable": "Could not match to XBRL reliably."}.get(xbrl_status, "")}

    ev = (40 if evidence_verified else 0) + (20 if has_snippet else 0) + (20 if has_location else 0) + (20 if has_url else 0)
    sig["evidence_completeness"] = {"score": ev, "why": "Snippet, location and URL recorded; evidence re-verified against the parsed filing."
                                    if ev == 100 else "Evidence record incomplete or failed re-verification."}

    total = sum(WEIGHTS[k] * sig[k]["score"] / 100 for k in WEIGHTS)
    return {"score": round(total, 2), "signals": sig, "weights": WEIGHTS,
            "formula": "Σ (weight_i × signal_i / 100) over 7 signals; weights sum to 100"}
