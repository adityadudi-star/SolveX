"""SEC XBRL Company Facts: ground-truth matching and annual history.

All logic is deterministic and works on the Company Facts JSON structure
(facts[taxonomy][concept]['units'][unit] -> list of fact entries with start/end/val/accn/fy/fp/form/filed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

ANNUAL_FORMS = {"10-K", "10-K/A", "10-K405", "10-KSB", "10-KT"}


def _d(s: str | None) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


@dataclass
class XFact:
    concept: str
    taxonomy: str
    value: float
    start: date | None
    end: date
    accn: str
    form: str
    fy: int | None
    fp: str | None
    filed: date | None
    unit: str

    def as_dict(self) -> dict[str, Any]:
        return {"concept": f"{self.taxonomy}:{self.concept}", "value": self.value, "start": str(self.start) if self.start else None,
                "end": str(self.end), "accn": self.accn, "form": self.form, "fy": self.fy, "fp": self.fp,
                "filed": str(self.filed) if self.filed else None, "unit": self.unit}


def split_concept(name: str) -> tuple[str, str]:
    if ":" in name:
        ns, c = name.split(":", 1)
        return ns, c
    return "us-gaap", name


def facts_for(companyfacts: dict, concept: str, taxonomy: str = "us-gaap", unit: str = "USD") -> list[XFact]:
    node = companyfacts.get("facts", {}).get(taxonomy, {}).get(concept)
    if not node:
        return []
    out: list[XFact] = []
    for e in node.get("units", {}).get(unit, []):
        end = _d(e.get("end"))
        if end is None or "val" not in e:
            continue
        out.append(XFact(concept, taxonomy, float(e["val"]), _d(e.get("start")), end, e.get("accn", ""), e.get("form", ""),
                         e.get("fy"), e.get("fp"), _d(e.get("filed")), unit))
    return out


def _is_annual(f: XFact, period_type: str) -> bool:
    if f.form not in ANNUAL_FORMS:
        return False
    if period_type == "instant":
        return f.start is None
    if f.start is None:
        return False
    return 340 <= (f.end - f.start).days <= 380


@dataclass
class MatchResult:
    status: str                      # matched|mismatched|missing|unable
    concept: str | None = None
    xbrl_value: float | None = None
    difference: float | None = None
    tolerance: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    accession: str | None = None
    unit: str | None = "USD"
    candidates: list[dict] = field(default_factory=list)
    note: str = ""
    concept_changed: bool = False


def match_metric(companyfacts: dict | None, *, concepts: list[str], period_type: str, period_end: date | None,
                 accession: str, extracted_value: float | None, scale: int | None, from_ix: bool,
                 compare_abs: bool = False, preferred_concept: str | None = None, unit: str = "USD") -> MatchResult:
    """Compare an extracted value to SEC XBRL ground truth for the right concept / period / unit / accession."""
    if not companyfacts:
        return MatchResult("unable", note="XBRL Company Facts unavailable; cannot verify.")
    if extracted_value is None or period_end is None:
        return MatchResult("unable", note="Extracted value or reporting period unknown; cannot match reliably.")
    ordered = ([preferred_concept] if preferred_concept else []) + [c for c in concepts if c != preferred_concept]
    seen_any: list[XFact] = []
    tol = 0.5 if from_ix else 0.5 * (10 ** (scale or 0))
    first_hit: MatchResult | None = None
    for idx, name in enumerate(ordered):
        tax, c = split_concept(name)
        facts = [f for f in facts_for(companyfacts, c, tax, unit) if f.end == period_end and _is_annual(f, period_type)]
        if not facts:
            continue
        seen_any += facts
        # filing-accession context where available: prefer facts reported in this very filing
        same_acc = [f for f in facts if f.accn == accession]
        pool = same_acc or facts
        vals = {round(f.value, 2) for f in pool}
        if len(vals) > 1 and not same_acc:
            # different filings reported different values for the same period (restatement) and ours isn't there
            return MatchResult("unable", concept=f"{tax}:{c}", period_end=period_end, candidates=[f.as_dict() for f in pool],
                               note="Multiple conflicting XBRL values for this period and none from this filing.")
        f = sorted(pool, key=lambda x: x.filed or date.min)[-1]
        xv = abs(f.value) if compare_abs else f.value
        ev = abs(extracted_value) if compare_abs else extracted_value
        diff = ev - xv
        res = MatchResult("matched" if abs(diff) <= tol else "mismatched", concept=f"{tax}:{c}", xbrl_value=f.value,
                          difference=diff, tolerance=tol, period_start=f.start, period_end=f.end, accession=f.accn,
                          candidates=[x.as_dict() for x in pool][:6], unit=unit,
                          note=("From the same filing accession." if same_acc else "Matched by period only (value not reported under this accession)."),
                          concept_changed=bool(preferred_concept and f"{tax}:{c}" != preferred_concept and idx > 0))
        if res.status == "matched":
            return res
        first_hit = first_hit or res
    if first_hit:
        return first_hit
    return MatchResult("missing", period_end=period_end,
                       note="No XBRL fact exists for any mapped concept, period and unit (the company may not tag this item).")


@dataclass
class HistoryPoint:
    end: date
    value: float
    accn: str
    filed: date | None
    concept: str


def annual_history(companyfacts: dict | None, *, concepts: list[str], period_type: str, period_end: date,
                   accession: str, years_back: int = 5) -> dict[str, Any]:
    """Prior annual values, as presented in the *current* filing where possible (comparable / restated basis).

    Returns {'points': [HistoryPoint...] newest-first (excluding current), 'restatements': [...], 'concept': str|None}
    """
    res: dict[str, Any] = {"points": [], "restatements": [], "concept": None}
    if not companyfacts:
        return res
    for name in concepts:
        tax, c = split_concept(name)
        allf = [f for f in facts_for(companyfacts, c, tax) if _is_annual(f, period_type)]
        if not allf:
            continue
        by_end: dict[date, list[XFact]] = {}
        for f in allf:
            by_end.setdefault(f.end, []).append(f)
        if period_end not in by_end:
            continue
        res["concept"] = f"{tax}:{c}"
        pts: list[HistoryPoint] = []
        for end, fs in sorted(by_end.items(), reverse=True):
            if end >= period_end - timedelta(days=200) or end < period_end - timedelta(days=366 * years_back + 40):
                continue
            # one point per fiscal year: use value shown in current filing if present, else latest-filed value
            cur = [f for f in fs if f.accn == accession]
            chosen = sorted(cur or fs, key=lambda x: x.filed or date.min)[-1]
            pts.append(HistoryPoint(end, chosen.value, chosen.accn, chosen.filed, f"{tax}:{c}"))
            # restatement: comparative number in current filing differs from the number originally reported
            orig = sorted([f for f in fs if f.accn != accession], key=lambda x: x.filed or date.min)
            if cur and orig and abs(orig[0].value - cur[0].value) > 0.5:
                res["restatements"].append({"period_end": str(end), "originally_reported": orig[0].value, "originally_reported_accn": orig[0].accn,
                                            "as_presented_now": cur[0].value, "accn": accession})
        # keep only one point per ~year (dedupe fiscal-year-end drift)
        dedup: list[HistoryPoint] = []
        for p in pts:
            if not dedup or (dedup[-1].end - p.end).days > 300:
                dedup.append(p)
        res["points"] = dedup
        return res
    return res
