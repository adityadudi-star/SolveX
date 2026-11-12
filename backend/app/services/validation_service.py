"""Deterministic financial validation checks. Every check stores inputs, formula, result, tolerance, status, explanation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.utils.catalog import METRIC_BY_KEY


@dataclass
class CheckResult:
    check_type: str
    name: str
    status: str                      # passed | warning | failed | skipped
    formula: str
    inputs: dict[str, Any]
    result: dict[str, Any]
    explanation: str
    tolerance: float | None = None
    blocking: bool = False           # a failed blocking check forces HUMAN_APPROVAL_REQUIRED
    metric_keys: list[str] = field(default_factory=list)


def pct_change(current: float, previous: float) -> float | None:
    """((current − previous) / |previous|) × 100 ; undefined when previous == 0."""
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def accounting_equation(assets: float | None, liabilities: float | None, equity: float | None, tol_pct: float) -> CheckResult:
    formula = "Total Assets = Total Liabilities + Shareholders' Equity"
    if None in (assets, liabilities, equity):
        missing = [n for n, v in (("Total Assets", assets), ("Total Liabilities", liabilities), ("Shareholders' Equity", equity)) if v is None]
        return CheckResult("accounting_equation", "Accounting equation", "failed", formula,
                           {"assets": assets, "liabilities": liabilities, "equity": equity}, {"missing": missing},
                           f"Cannot evaluate: {', '.join(missing)} not available. Missing data is never treated as zero.",
                           tol_pct, blocking=True, metric_keys=["total_assets", "total_liabilities", "shareholders_equity"])
    diff = assets - (liabilities + equity)
    base = abs(assets) or 1.0
    rel = abs(diff) / base * 100
    status = "passed" if rel <= tol_pct else ("warning" if rel <= tol_pct * 10 else "failed")
    return CheckResult("accounting_equation", "Accounting equation", status, formula,
                       {"assets": assets, "liabilities": liabilities, "equity": equity},
                       {"difference": diff, "difference_pct_of_assets": round(rel, 6), "liabilities_plus_equity": liabilities + equity},
                       f"Assets − (Liabilities + Equity) = {diff:,.0f} ({rel:.4f}% of assets) vs tolerance {tol_pct}%."
                       + ("" if status == "passed" else " Difference may reflect non-controlling interests or extraction error; reviewer attention advised."),
                       tol_pct, blocking=(status == "failed"), metric_keys=["total_assets", "total_liabilities", "shareholders_equity"])


def missing_data(found: dict[str, bool]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for key, ok in found.items():
        md = METRIC_BY_KEY[key]
        if ok:
            out.append(CheckResult("missing_data", f"{md.label} present", "passed", "metric found with evidence", {"metric": key}, {"found": True},
                                   f"{md.label} was located in the filing.", metric_keys=[key]))
        else:
            out.append(CheckResult("missing_data", f"{md.label} present", "failed" if md.mandatory else "warning", "metric found with evidence",
                                   {"metric": key}, {"found": False},
                                   f"{md.label} was not found in this filing. It is recorded as missing, never as zero.",
                                   blocking=md.mandatory, metric_keys=[key]))
    return out


def period_consistency(periods: dict[str, tuple[date | None, str | None]], filing_period_end: date | None) -> CheckResult:
    formula = "all metric period_end dates == filing period of report"
    bad = {k: str(v[0]) for k, v in periods.items() if v[0] is not None and filing_period_end and v[0] != filing_period_end}
    unknown = [k for k, v in periods.items() if v[0] is None]
    if bad:
        return CheckResult("period_mismatch", "Reporting-period consistency", "failed", formula,
                           {"filing_period_end": str(filing_period_end), "periods": {k: str(v[0]) for k, v in periods.items()}},
                           {"mismatched": bad}, f"{len(bad)} metric(s) are dated differently from the filing period.", blocking=True,
                           metric_keys=list(bad))
    if unknown:
        return CheckResult("period_mismatch", "Reporting-period consistency", "warning", formula,
                           {"filing_period_end": str(filing_period_end)}, {"unknown": unknown},
                           "Period could not be established for some metrics.", metric_keys=unknown)
    return CheckResult("period_mismatch", "Reporting-period consistency", "passed", formula,
                       {"filing_period_end": str(filing_period_end)}, {"mismatched": {}},
                       "All extracted metrics belong to the filing's fiscal period.")


def unit_consistency(units: dict[str, tuple[str | None, int | None]]) -> CheckResult:
    formula = "all metrics share one currency and one displayed scale"
    currencies = {c for c, _ in units.values() if c}
    scales = {s for _, s in units.values() if s is not None}
    missing_scale = [k for k, (_, s) in units.items() if s is None]
    if len(currencies) > 1:
        return CheckResult("unit_mismatch", "Currency / unit consistency", "failed", formula,
                           {"units": {k: list(v) for k, v in units.items()}}, {"currencies": sorted(currencies)},
                           f"Multiple currencies detected: {sorted(currencies)}.", blocking=True, metric_keys=list(units))
    if len(scales) > 1:
        return CheckResult("unit_mismatch", "Currency / unit consistency", "warning", formula,
                           {"units": {k: list(v) for k, v in units.items()}}, {"scales": sorted(scales)},
                           f"Different display scales (10^{sorted(scales)}) across statements; values were normalised using each table's stated scale.",
                           metric_keys=list(units))
    if missing_scale:
        return CheckResult("unit_mismatch", "Currency / unit consistency", "warning", formula,
                           {"units": {k: list(v) for k, v in units.items()}}, {"scale_not_stated": missing_scale},
                           "Some tables do not state their unit scale.", metric_keys=missing_scale)
    return CheckResult("unit_mismatch", "Currency / unit consistency", "passed", formula,
                       {"units": {k: list(v) for k, v in units.items()}}, {"currencies": sorted(currencies), "scales": sorted(scales)},
                       "A single currency and consistent scale across extracted metrics.")


def sign_and_scale_checks(key: str, current: float, previous: float | None) -> list[CheckResult]:
    md = METRIC_BY_KEY[key]
    out: list[CheckResult] = []
    if md.nonnegative:
        ok = current >= 0
        out.append(CheckResult("unexpected_sign", f"{md.label}: expected sign", "passed" if ok else "failed", "value >= 0",
                               {"value": current}, {"negative": not ok},
                               f"{md.label} is {'non-negative as expected' if ok else 'negative, which is unexpected for this item'}.",
                               blocking=not ok, metric_keys=[key]))
    if previous not in (None, 0):
        if (current > 0) != (previous > 0) and current != 0:
            out.append(CheckResult("unexpected_sign_change", f"{md.label}: sign change vs prior year", "warning", "sign(current) == sign(previous)",
                                   {"current": current, "previous": previous}, {"sign_changed": True},
                                   f"{md.label} changed sign year over year ({previous:,.0f} → {current:,.0f}).", metric_keys=[key]))
        ratio = abs(current / previous)
        if ratio >= 100 or ratio <= 0.01:
            out.append(CheckResult("unusual_scaling", f"{md.label}: unusual scaling", "failed", "0.01 < |current/previous| < 100",
                                   {"current": current, "previous": previous}, {"ratio": ratio},
                                   f"Current value is {ratio:,.2f}× the prior year — consistent with a thousands/millions scaling error.",
                                   blocking=True, metric_keys=[key]))
    return out


def restatement_check(key: str, restatements: list[dict]) -> CheckResult:
    md = METRIC_BY_KEY[key]
    if restatements:
        r = restatements[0]
        return CheckResult("restatement", f"{md.label}: restatement identification", "warning", "comparative value in this filing != value originally reported",
                           {"period_end": r["period_end"]}, r,
                           f"Prior-year {md.label} appears restated: originally {r['originally_reported']:,.0f}, now {r['as_presented_now']:,.0f}. "
                           "Year-over-year comparison uses the restated comparative.", metric_keys=[key])
    return CheckResult("restatement", f"{md.label}: restatement identification", "passed", "comparative value in this filing == value originally reported",
                       {}, {"restated": False}, "No restatement of the comparative period detected in XBRL history.", metric_keys=[key])


def segment_consistency() -> CheckResult:
    return CheckResult(
        "segment_consistency", "Segment consistency", "skipped", "Σ segment values == consolidated value",
        {}, {"applicable": False},
        "Segment-level facts are dimensional XBRL contexts and are not comparable across companies in the headline metrics; "
        "check skipped honestly rather than approximated.")
