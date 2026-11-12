"""Pure-Python engine tests: decision rules, anomalies, validation formulas, parsing, settings guard rails, append-only history."""
from __future__ import annotations

import pytest

from app.models import AppendOnlyError, ReviewEvent, ThresholdChange
from app.services import validation_service as v
from app.services.anomaly_service import detect
from app.services.decision_service import DecisionInput, decide, overall_decision
from app.services.filing_parser import parse_display_number, parse_filing
from app.services.settings_service import SettingsError, get_thresholds, update_thresholds
from app.utils.catalog import DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED

APPROVAL, REVIEW = 98.0, 90.0


def dec(**kw):
    base = dict(found=True, confidence=100.0, evidence_verified=True, validation_statuses=[("passed", False)], anomaly_status="normal",
                anomaly_mandatory=False, xbrl_status="matched")
    base.update(kw)
    return decide(DecisionInput(**base), approval=APPROVAL, review=REVIEW)


# ---- required decision scenarios
def test_normal_audit_fully_passed():
    assert dec().decision == DECISION_PASSED


def test_non_blocking_warning_recommends_human_consideration():
    assert dec(validation_statuses=[("warning", False)]).decision == DECISION_RECOMMENDED
    assert dec(anomaly_status="warning").decision == DECISION_RECOMMENDED
    assert dec(confidence=94.0).decision == DECISION_RECOMMENDED          # 90..98 band


def test_low_confidence_requires_human_approval():
    assert dec(confidence=89.9).decision == DECISION_REQUIRED


def test_critical_accounting_failure_requires_human_approval():
    assert dec(validation_statuses=[("failed", True)]).decision == DECISION_REQUIRED


def test_critical_100_confidence_with_mandatory_anomaly_requires_human_approval():
    """Revenue $200M -> $500M (+150%), threshold 50%, confidence 100, accounting passed => HUMAN APPROVAL REQUIRED."""
    a = detect("revenue", 500e6, [200e6], mandatory_pct=50, warning_pct=25)
    assert a.pct_change == pytest.approx(150.0)
    assert a.abs_change == pytest.approx(300e6)
    assert a.mandatory and a.status == "mandatory"
    d = dec(confidence=100.0, anomaly_status=a.status, anomaly_mandatory=a.mandatory)
    assert d.decision == DECISION_REQUIRED
    assert any(r["rule"] == "mandatory_anomaly" for r in d.rules_triggered)


def test_highest_severity_rule_wins():
    d = dec(confidence=95.0, validation_statuses=[("warning", False), ("failed", True)])
    assert d.decision == DECISION_REQUIRED
    assert overall_decision([DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED]) == DECISION_REQUIRED


def test_missing_mandatory_evidence_and_xbrl_mismatch_and_unit_problem():
    assert dec(found=False).decision == DECISION_REQUIRED
    assert dec(found=False, mandatory=False).decision == DECISION_RECOMMENDED   # missing optional metric: never zero, never silently fine
    assert dec(xbrl_status="mismatched").decision == DECISION_REQUIRED
    assert dec(serious_unit_or_period=True).decision == DECISION_REQUIRED


def test_decision_engine_has_no_llm_input():
    import inspect
    assert not any("llm" in p.lower() for p in inspect.signature(decide).parameters)


# ---- formulas
def test_pct_change_formula_with_negative_and_zero_baselines():
    assert v.pct_change(150, 100) == 50.0
    assert v.pct_change(-50, -100) == pytest.approx(50.0)        # divides by |previous|
    assert v.pct_change(10, 0) is None


def test_zero_baseline_is_flagged_not_crashing():
    a = detect("revenue", 10.0, [0.0], mandatory_pct=50, warning_pct=25)
    assert a.pct_change is None and a.status == "warning" and "zero" in a.explanation.lower()


def test_missing_history_is_insufficient_history():
    a = detect("revenue", 10.0, [], mandatory_pct=50, warning_pct=25)
    assert a.status == "insufficient_history" and "Insufficient History" in a.explanation


def test_accounting_equation_bands_and_missing():
    assert v.accounting_equation(5000, 3000, 2000, 0.1).status == "passed"
    assert v.accounting_equation(5000, 3000, 1990, 0.1).status == "warning"      # 0.2% off
    c = v.accounting_equation(5000, 3500, 2000, 0.1)
    assert c.status == "failed" and c.blocking and c.formula and c.inputs and c.tolerance == 0.1
    m = v.accounting_equation(5000, None, 2000, 0.1)
    assert m.status == "failed" and "never treated as zero" in m.explanation


def test_unit_checks_mixed_currency_and_scaling():
    assert v.unit_consistency({"a": ("USD", 6), "b": ("EUR", 6)}).status == "failed"
    assert v.unit_consistency({"a": ("USD", 6), "b": ("USD", 3)}).status == "warning"
    assert v.unit_consistency({"a": ("USD", 6), "b": ("USD", 6)}).status == "passed"
    sc = v.sign_and_scale_checks("revenue", 1_000_000.0, 1_000.0)          # 1000x jump = thousands/millions error
    assert any(c.check_type == "unusual_scaling" and c.status == "failed" for c in sc)
    assert any(c.check_type == "unexpected_sign" and c.status == "failed" for c in v.sign_and_scale_checks("total_assets", -5.0, 5.0))


def test_period_mismatch_detected():
    from datetime import date
    r = v.period_consistency({"revenue": (date(2023, 12, 31), "duration")}, date(2024, 12, 31))
    assert r.status == "failed" and r.blocking


# ---- parsing
def test_parse_numbers_parentheses_and_units():
    assert parse_display_number("(1,234)") == (-1234.0, True)
    assert parse_display_number("$ 12,345.6") == (12345.6, False)
    assert parse_display_number("—") is None
    assert parse_display_number("abc") is None
    assert parse_display_number("(12") == (-12.0, True)


def test_column_chosen_by_context_when_oldest_year_is_first():
    html = """<html><body><ix:header><ix:resources>
      <xbrli:context id="A"><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-12-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="B"><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
      </ix:resources></ix:header>
      <p>CONSOLIDATED STATEMENTS OF OPERATIONS (in thousands)</p>
      <table><tr><td></td><td>2023</td><td>2024</td></tr>
      <tr><td>Net sales</td><td><ix:nonFraction name="us-gaap:Revenues" contextRef="A" unitRef="usd" scale="3">100</ix:nonFraction></td>
          <td><ix:nonFraction name="us-gaap:Revenues" contextRef="B" unitRef="usd" scale="3">300</ix:nonFraction></td></tr>
      <tr><td>Operating income</td><td>1</td><td>2</td></tr><tr><td>Net income</td><td>1</td><td>2</td></tr><tr><td>Income tax</td><td>1</td><td>2</td></tr>
      <tr><td>Earnings per share</td><td>1</td><td>2</td></tr></table></body></html>"""
    from datetime import date
    from app.services.extraction_service import extract_metrics
    c = next(x for x in extract_metrics(parse_filing(html), date(2024, 12, 31), "u") if x.metric_key == "revenue")
    assert c.found and c.value == 300_000 and c.detail["column_choice"] == "ix_context" and c.scale == 3


def test_missing_metric_is_missing_not_zero():
    from datetime import date
    from app.services.extraction_service import extract_metrics
    cands = extract_metrics(parse_filing("<html><body><p>nothing here</p></body></html>"), date(2024, 12, 31), "u")
    assert all((not c.found) and c.value is None for c in cands)


# ---- settings guard rails, append-only
def test_settings_guard_rails_and_change_history(env):
    from app.database.session import session_scope
    with session_scope() as s:
        with pytest.raises(SettingsError):
            update_thresholds(s, {"approval_confidence": 60}, "x", None)       # cannot loosen below guard rail
        with pytest.raises(SettingsError):
            update_thresholds(s, {"review_confidence": 99}, "x", None)         # review must be < approval
        with pytest.raises(SettingsError):
            update_thresholds(s, {"disable_mandatory_review": 1}, "x", None)   # not a setting
        out = update_thresholds(s, {"anomaly_mandatory_pct": 60}, "ada", "tuning")
        assert out["anomaly_mandatory_pct"] == 60 and get_thresholds(s)["anomaly_mandatory_pct"] == 60
        assert s.query(ThresholdChange).count() == 1
        row = s.query(ThresholdChange).first()
        row.new_value = 1
        with pytest.raises(AppendOnlyError):
            s.flush()
        s.rollback()


def test_review_history_is_append_only(env):
    from app.database.session import session_scope
    wid = env.audit(values={**__import__("tests.fixtures", fromlist=["BASE"]).BASE, "revenue": (2500, 1000, 950)})
    api = env.api()
    pend = api.get("/api/reviews/pending").json()["pending"]
    from tests.conftest import REVIEW_HEADERS
    api.post(f"/api/reviews/{pend[0]['id']}/approve", headers=REVIEW_HEADERS, json={"notes": "ok"})
    with session_scope() as s:
        ev = s.query(ReviewEvent).first()
        ev.notes = "tampered"
        with pytest.raises(AppendOnlyError):
            s.flush()
        s.rollback()
        s.delete(ev)
        with pytest.raises(AppendOnlyError):
            s.flush()
        s.rollback()
    _ = wid
