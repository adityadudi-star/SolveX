"""Anomaly detection = investigation signals, not proof of fraud. Values are never modified to hide anomalies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.services.validation_service import pct_change
from app.utils.catalog import METRIC_BY_KEY


@dataclass
class AnomalyResult:
    kind: str
    status: str            # normal | warning | mandatory | insufficient_history
    severity: str          # none | low | moderate | high
    mandatory: bool
    current: float | None
    previous: float | None
    baseline: float | None
    abs_change: float | None
    pct_change: float | None
    threshold: float
    explanation: str
    detail: dict[str, Any] = field(default_factory=dict)


KIND_BY_METRIC = {
    "revenue": "unusual_revenue_movement", "net_income": "sudden_net_income_change",
    "total_assets": "large_balance_sheet_movement", "total_liabilities": "large_balance_sheet_movement",
    "shareholders_equity": "large_balance_sheet_movement", "cash_and_equivalents": "large_balance_sheet_movement",
    "operating_cash_flow": "unusual_cash_flow_change", "capital_expenditure": "unusual_cash_flow_change",
    "operating_expenses": "unusual_expense_movement",
}


def detect(key: str, current: float | None, history_values: list[float], *, mandatory_pct: float, warning_pct: float,
           concept_changed: bool = False) -> AnomalyResult:
    """history_values: prior annual values, newest first. mandatory_pct / warning_pct are |YoY %| thresholds."""
    md = METRIC_BY_KEY[key]
    kind = KIND_BY_METRIC.get(key, "metric_movement")
    if current is None:
        return AnomalyResult(kind, "insufficient_history", "low", False, None, None, None, None, None, mandatory_pct,
                             f"{md.label} was not extracted, so no historical comparison is possible.")
    if not history_values:
        return AnomalyResult("missing_history", "insufficient_history", "low", False, current, None, None, None, None, mandatory_pct,
                             f"Insufficient History: no prior-year XBRL value for {md.label}, so year-over-year anomaly checks could not run. "
                             "This is not evidence of an anomaly; a reviewer may wish to consider it.")
    prev = history_values[0]
    baseline = float(np.mean(history_values[:3]))
    chg = current - prev
    pc = pct_change(current, prev)
    detail = {"history_values": history_values[:5], "baseline_basis": f"mean of last {min(3, len(history_values))} prior annual value(s)",
              "concept_changed": concept_changed, "formula": "((current − previous) / |previous|) × 100"}
    if pc is None:
        return AnomalyResult(kind, "warning", "moderate", False, current, prev, baseline, chg, None, mandatory_pct,
                             f"Prior-year {md.label} is zero, so a percentage change is undefined (zero baseline). "
                             f"Absolute change is {chg:,.0f}; flagged for consideration, not as proof of a problem.", detail)
    a = abs(pc)
    if a >= mandatory_pct:
        status, sev, mand = "mandatory", "high", True
        why = (f"{md.label} moved {pc:+.1f}% year over year ({prev:,.0f} → {current:,.0f}), at or above the {mandatory_pct:g}% mandatory-review threshold. "
               "This is an investigation signal, not proof of misstatement or fraud.")
    elif a >= warning_pct:
        status, sev, mand = "warning", "moderate", False
        why = (f"{md.label} moved {pc:+.1f}% year over year, above the {warning_pct:g}% warning level but below the {mandatory_pct:g}% mandatory threshold.")
    else:
        status, sev, mand = "normal", "none", False
        why = f"{md.label} moved {pc:+.1f}% year over year, within the normal range (< {warning_pct:g}%)."
    if concept_changed:
        why += " The XBRL concept used for this item differs from earlier filings, which can explain part of the movement."
        if status == "normal":
            status, sev = "warning", "low"
    return AnomalyResult(kind, status, sev, mand, current, prev, baseline, chg, pc,
                         mandatory_pct if status in ("mandatory", "normal") else warning_pct if status == "warning" else mandatory_pct,
                         why, detail)
