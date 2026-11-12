"""Three-level decision engine. Pure deterministic Python — no LLM can influence or override the outcome.

The highest-severity applicable rule determines the decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.catalog import DECISION_PASSED, DECISION_RANK, DECISION_RECOMMENDED, DECISION_REQUIRED


@dataclass
class DecisionInput:
    found: bool
    mandatory: bool = True
    confidence: float = 0.0
    evidence_verified: bool = True
    validation_statuses: list[tuple[str, bool]] = field(default_factory=list)  # (status, blocking)
    anomaly_status: str = "normal"      # normal | warning | mandatory | insufficient_history
    anomaly_mandatory: bool = False
    xbrl_status: str = "matched"        # matched|mismatched|missing|unable
    serious_unit_or_period: bool = False


@dataclass
class Decision:
    decision: str
    reasons: list[str]
    rules_triggered: list[dict]


def decide(inp: DecisionInput, *, approval: float, review: float) -> Decision:
    """Evaluate every rule and return the highest-severity outcome."""
    triggered: list[tuple[str, str, str]] = []   # (level, rule, reason)
    R, C, P = DECISION_REQUIRED, DECISION_RECOMMENDED, DECISION_PASSED

    if not inp.found:
        if inp.mandatory:
            triggered.append((R, "missing_mandatory_evidence", "Metric not found in the filing; mandatory evidence is missing."))
        else:
            triggered.append((C, "missing_optional_metric", "Optional metric not found in the filing; recorded as missing (never zero)."))
    else:
        if not inp.evidence_verified:
            triggered.append((R, "evidence_unverified", "Source evidence could not be re-verified against the filing."))
        if inp.confidence < review:
            triggered.append((R, "low_confidence", f"Extraction confidence {inp.confidence:.1f} is below the {review:g} review floor."))
        elif inp.confidence < approval:
            triggered.append((C, "borderline_confidence", f"Extraction confidence {inp.confidence:.1f} is below the {approval:g} approval threshold."))
        for status, blocking in inp.validation_statuses:
            if status == "failed" and blocking:
                triggered.append((R, "critical_accounting_failure", "A blocking accounting/consistency check failed."))
            elif status in ("failed", "warning"):
                triggered.append((C, "validation_warning", "A non-blocking validation check raised a warning."))
        if inp.anomaly_mandatory:
            triggered.append((R, "mandatory_anomaly", "A mandatory-review anomaly was detected (confidence cannot override this)."))
        elif inp.anomaly_status in ("warning", "insufficient_history"):
            triggered.append((C, "non_mandatory_anomaly" if inp.anomaly_status == "warning" else "insufficient_history",
                              "Anomaly warning raised." if inp.anomaly_status == "warning" else "Insufficient history for anomaly analysis."))
        if inp.xbrl_status == "mismatched":
            triggered.append((R, "xbrl_mismatch", "Extracted value disagrees with SEC XBRL ground truth."))
        elif inp.xbrl_status in ("missing", "unable"):
            triggered.append((C, "xbrl_unverified", "Value could not be corroborated by SEC XBRL."))
        if inp.serious_unit_or_period:
            triggered.append((R, "unit_or_period_inconsistency", "Serious unit or period inconsistency detected."))

    level = P
    for lv, _, _ in triggered:
        if DECISION_RANK[lv] > DECISION_RANK[level]:
            level = lv
    reasons = [r for lv, _, r in triggered if lv == level] if level != P else ["All mandatory checks passed with no warnings."]
    return Decision(level, reasons, [{"level": lv, "rule": rule, "reason": rs} for lv, rule, rs in triggered])


def overall_decision(metric_decisions: list[str]) -> str:
    if not metric_decisions:
        return DECISION_REQUIRED
    return max(metric_decisions, key=lambda d: DECISION_RANK[d])
