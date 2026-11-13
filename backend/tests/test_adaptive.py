"""Adaptive Threshold Engine tests: learning conditions, per-metric independence, persistence, safeguards, audit log."""
from __future__ import annotations

import threading

import pytest

from app.database.session import session_scope
from app.models import AdaptiveAdjustment, AdaptiveFeedback, AdaptiveThreshold, AppendOnlyError, AuditWorkflow, MetricResult
from app.services import adaptive_service as svc
from app.utils.catalog import DECISION_REQUIRED
from tests.conftest import REVIEW_HEADERS

LOW = dict(inline=False, facts_status=404)    # plain-HTML table, no XBRL -> confidence ~79 (just below an 80 floor)


def setup_floor(env, floor=80):
    env.use(**LOW)
    api = env.api()
    r = api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"review_confidence": floor, "reason": "adaptive test"})
    assert r.status_code == 200, r.text
    return api


def metric(wid, key="revenue") -> MetricResult:
    with session_scope() as s:
        return s.query(MetricResult).filter_by(workflow_id=wid, metric_key=key).one()


def low_audit(env) -> str:
    return env.audit(**LOW)


def review(api, wid, action="approve", key="revenue", notes="ok"):
    mid = metric(wid, key).id
    body = {"notes": notes}
    if action == "correct":
        body["corrected_value"] = 1.0
    return api.post(f"/api/reviews/{mid}/{action}", headers=REVIEW_HEADERS, json=body)


def overview(api):
    o = api.get("/api/adaptive/overview").json()
    return {m["metric_key"]: m for m in o["metrics"]}, o


def run_reviews(env, api, n, action="approve"):
    last = None
    for _ in range(n):
        wid = low_audit(env)
        last = review(api, wid, action)
        assert last.status_code == 200, last.text
    return last


# --------------------------------------------------------------- the 9-step scenario from the brief
def test_full_adaptive_workflow(env):
    api = setup_floor(env, 80)
    m0, _ = overview(api)
    assert m0["revenue"]["current"] == 80 and m0["revenue"]["source"] == "default" and m0["net_income"]["current"] == 80   # 1. 80%

    wid1 = low_audit(env)                                                                                                # 2. ~77% item
    rev = metric(wid1)
    assert 76 <= rev.confidence < 80
    assert rev.decision == DECISION_REQUIRED and rev.review_status == "pending"                                          # 3. flagged
    assert rev.explanation["threshold_applied"] == {"value": 80.0, "source": "default", "epoch": 0}

    r = review(api, wid1)                                                                                                # 4. reviewers approve
    assert r.json()["adaptive"]["adjusted"] is None
    for _ in range(8):                                                                                                   # 9 approvals: not enough
        assert review(api, low_audit(env)).json()["adaptive"]["adjusted"] is None
    assert overview(api)[0]["revenue"]["current"] == 80
    assert overview(api)[0]["revenue"]["window"]["reviews"] == 9

    last = review(api, low_audit(env)).json()                                                                            # 10th approval
    adj = last["adaptive"]["adjusted"]
    assert adj and adj["previous"] == 80 and adj["new"] == 75 and "between 76% and 79%" in adj["reason"]                 # 5. 80 -> 75

    m1, o = overview(api)
    rv = m1["revenue"]
    assert rv["current"] == 75 and rv["previous"] == 80 and rv["default"] == 80 and rv["source"] == "auto"              # 5b. auto-tuned badge data
    assert rv["adjustments"] == 1 and rv["last_adjusted_at"] and rv["last_auto"]["reviews_considered"] == 10 and rv["last_auto"]["approval_rate"] == 100
    assert rv["window"]["reviews"] == 0, "old-epoch feedback must not count toward the next adjustment"

    new_wid = low_audit(env)                                                                                              # 7. same confidence now passes the floor
    nr = metric(new_wid)
    assert 76 <= nr.confidence < 80 and nr.decision != DECISION_REQUIRED and nr.review_status != "pending"
    assert nr.explanation["threshold_applied"]["value"] == 75 and nr.explanation["threshold_applied"]["source"] == "auto"
    assert not any(x["rule"] == "low_confidence" for x in nr.explanation["rules_triggered"])

    old = metric(wid1)                                                                                                    # history untouched
    assert old.decision == DECISION_REQUIRED and old.explanation["threshold_applied"]["value"] == 80

    with session_scope() as s:                                                                                            # 8. persisted in the DB
        row = s.get(AdaptiveThreshold, "revenue")
        assert row.current_threshold == 75 and row.default_threshold == 80 and row.source == "auto"
    assert overview(env.api())[0]["revenue"]["current"] == 75

    assert m1["net_income"]["current"] == 80 and m1["net_income"]["source"] == "default"                                  # 9. independent metrics
    h = api.get("/api/adaptive/history").json()["history"]
    assert len(h) == 1 and h[0]["kind"] == "auto" and h[0]["reviews_considered"] == 10 and h[0]["approval_rate"] == 100 and h[0]["metric_key"] == "revenue"


# --------------------------------------------------------------- safeguards
def test_low_approval_rate_does_not_tune(env):
    api = setup_floor(env)
    for i in range(10):
        wid = low_audit(env)
        assert review(api, wid, "approve" if i < 7 else "reject").status_code == 200       # 70% < 80%
    assert overview(api)[0]["revenue"]["current"] == 80
    assert overview(api)[0]["revenue"]["window"]["reviews"] == 10 and overview(api)[0]["revenue"]["window"]["rate"] == 70


def test_correct_counts_as_not_approved(env):
    api = setup_floor(env)
    for i in range(10):
        review(api, low_audit(env), "approve" if i < 7 else "correct")
    assert overview(api)[0]["revenue"]["current"] == 80


def test_bounds_respected(env):
    api = setup_floor(env)
    assert api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"min_threshold": 78}).status_code == 200
    run_reviews(env, api, 10)
    assert overview(api)[0]["revenue"]["current"] == 80          # 80 - 5 = 75 < min 78 -> refused
    assert api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"min_threshold": 99}).status_code == 422


def test_auto_tuning_can_be_disabled_globally_and_per_metric(env):
    api = setup_floor(env)
    assert api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"auto_tuning_enabled": 0}).status_code == 200
    run_reviews(env, api, 10)
    m, o = overview(api)
    assert m["revenue"]["current"] == 80 and o["totals"]["reviews"] == 10          # feedback still logged, nothing tuned
    api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"auto_tuning_enabled": 1})
    assert api.post("/api/adaptive/revenue/auto", headers=REVIEW_HEADERS, json={"paused": True}).json()["auto_paused"] is True
    with session_scope() as s:
        assert svc.maybe_autotune(s, "revenue") is None
        s.commit()
    api.post("/api/adaptive/revenue/auto", headers=REVIEW_HEADERS, json={"paused": False})
    with session_scope() as s:
        assert svc.maybe_autotune(s, "revenue") is not None          # conditions were already satisfied
        s.commit()
    assert overview(api)[0]["revenue"]["current"] == 75


def test_manual_set_reset_and_source_distinction(env):
    api = setup_floor(env)
    assert api.post("/api/adaptive/revenue/set", json={"value": 85, "reason": "x y z"}).status_code == 401
    assert api.post("/api/adaptive/revenue/set", headers=REVIEW_HEADERS, json={"value": 40, "reason": "too low"}).status_code == 422
    assert api.post("/api/adaptive/revenue/set", headers=REVIEW_HEADERS, json={"value": 99, "reason": "too high"}).status_code == 422
    ok = api.post("/api/adaptive/revenue/set", headers=REVIEW_HEADERS, json={"value": 85, "reason": "stricter for revenue"})
    assert ok.status_code == 200
    m, _ = overview(api)
    assert m["revenue"]["current"] == 85 and m["revenue"]["source"] == "manual" and m["revenue"]["adjustments"] == 0   # manual != auto
    run_reviews(env, api, 10)                                      # approvals at 85: window 81..84, but manual pin => no auto change
    # (item confidence ~78 is below 81, so not even in the learning window)
    assert overview(api)[0]["revenue"]["current"] == 85
    r = api.post("/api/adaptive/revenue/reset", headers=REVIEW_HEADERS, json={"reason": "back to default"})
    assert r.status_code == 200 and r.json()["adjustment"]["new"] == 80 and r.json()["adjustment"]["kind"] == "reset"
    m, _ = overview(api)
    assert m["revenue"]["current"] == 80 and m["revenue"]["source"] == "default"
    kinds = [h["kind"] for h in api.get("/api/adaptive/history").json()["history"]]
    assert kinds == ["reset", "manual"]


def test_reset_after_auto_tune_restores_original_and_relearns_cleanly(env):
    api = setup_floor(env)
    run_reviews(env, api, 10)
    assert overview(api)[0]["revenue"]["current"] == 75
    assert api.post("/api/adaptive/reset-all", headers=REVIEW_HEADERS, json={"reason": "undo"}).json()["reset"] == 1
    m, _ = overview(api)
    assert m["revenue"]["current"] == 80 and m["revenue"]["source"] == "default" and m["revenue"]["adjustments"] == 1   # history of the auto change kept
    assert m["revenue"]["window"]["reviews"] == 0


def test_feedback_is_evaluated_against_the_threshold_active_when_decided(env):
    api = setup_floor(env)
    wid_old = low_audit(env)                       # flagged under 80
    run_reviews(env, api, 10)                      # -> tuned to 75 (epoch 1)
    review(api, wid_old)                           # late review of an item decided under the OLD (80) threshold
    with session_scope() as s:
        fb = s.query(AdaptiveFeedback).filter_by(metric_id=metric(wid_old).id).one()
        assert fb.threshold_at_decision == 80 and fb.epoch == 0 and fb.eligible
        row = s.get(AdaptiveThreshold, "revenue")
        assert svc.window_stats(s, row, svc.get_config(s))["reviews"] == 0       # not counted toward the new (75) epoch


def test_duplicate_reviews_not_learned_twice(env):
    api = setup_floor(env)
    wid = low_audit(env)
    assert review(api, wid).status_code == 200
    assert review(api, wid).status_code == 409                                     # review service blocks the 2nd review
    with session_scope() as s:
        m = s.query(MetricResult).filter_by(workflow_id=wid, metric_key="revenue").one()
        ev = m.reviews[0]
        assert svc.record_feedback(s, m, ev) is None                               # and the engine would ignore it anyway
        assert s.query(AdaptiveFeedback).filter_by(metric_id=m.id).count() == 1


def test_only_pure_low_confidence_flags_teach_the_engine():
    class M:                                                                        # stub MetricResult
        found, confidence = True, 78.0
        def __init__(self, rules):
            self.explanation = {"threshold_applied": {"value": 80.0, "epoch": 0, "source": "default"}, "rules_triggered": rules}
    lc = {"level": "HUMAN_APPROVAL_REQUIRED", "rule": "low_confidence"}
    an = {"level": "HUMAN_APPROVAL_REQUIRED", "rule": "mandatory_anomaly"}
    warn = {"level": "PASSED_HUMAN_CONSIDERATION_RECOMMENDED", "rule": "xbrl_unverified"}
    assert svc._eligibility(M([lc, warn]))[0] is True
    assert svc._eligibility(M([lc, an]))[0] is False
    assert svc._eligibility(M([an]))[0] is False
    legacy = M([lc]); legacy.explanation = {}
    assert svc._eligibility(legacy)[0] is False


def test_concurrent_evaluation_adjusts_exactly_once(env):
    api = setup_floor(env)
    api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"auto_tuning_enabled": 0})
    run_reviews(env, api, 10)
    api.patch("/api/adaptive/config", headers=REVIEW_HEADERS, json={"auto_tuning_enabled": 1})
    results = []

    def worker():
        with session_scope() as s:
            results.append(svc.maybe_autotune(s, "revenue") is not None)
    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(results) == 1
    with session_scope() as s:
        assert s.query(AdaptiveAdjustment).filter_by(metric_key="revenue", kind="auto").count() == 1
        assert s.get(AdaptiveThreshold, "revenue").current_threshold == 75


def test_cooldown_blocks_back_to_back_adjustments(env):
    api = setup_floor(env)
    run_reviews(env, api, 10)                                                       # 80 -> 75
    wids = [low_audit(env) for _ in range(10)]                                      # 10 more qualifying approvals under the new 75 floor
    with session_scope() as s:
        row = s.get(AdaptiveThreshold, "revenue")
        assert row.current_threshold == 75
        for w in wids:
            mm = s.query(MetricResult).filter_by(workflow_id=w, metric_key="revenue").one()
            s.add(AdaptiveFeedback(metric_id=mm.id, workflow_id=w, metric_key="revenue", confidence=71.0, threshold_at_decision=75.0,
                                   epoch=row.epoch, action="approve", reviewer="t", eligible=True))
        s.commit()
        assert svc.window_stats(s, row, svc.get_config(s))["reviews"] == 10
        assert svc.maybe_autotune(s, "revenue") is None                             # blocked by the default 60-minute cooldown
        s.rollback()
        assert svc.maybe_autotune(s, "revenue", now=row.last_adjusted_at + __import__("datetime").timedelta(minutes=61)) is not None   # allowed later
        s.rollback()


def test_adaptive_logs_are_append_only(env):
    api = setup_floor(env)
    run_reviews(env, api, 10)
    with session_scope() as s:
        a = s.query(AdaptiveAdjustment).first()
        a.reason = "tampered"
        with pytest.raises(AppendOnlyError):
            s.flush()
        s.rollback()
        f = s.query(AdaptiveFeedback).first()
        s.delete(f)
        with pytest.raises(AppendOnlyError):
            s.flush()
        s.rollback()


def test_global_floor_change_propagates_only_to_untouched_metrics(env):
    api = setup_floor(env, 80)
    run_reviews(env, api, 10)                                                       # revenue tuned to 75
    api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"review_confidence": 85})
    m, _ = overview(api)
    assert m["revenue"]["current"] == 75 and m["revenue"]["source"] == "auto"
    assert m["net_income"]["current"] == 85 and m["net_income"]["default"] == 85


def test_default_behaviour_is_unchanged_when_nothing_is_tuned(env):
    env.use()
    m, _ = overview(env.api())
    assert {v["current"] for v in m.values()} == {90} and {v["source"] for v in m.values()} == {"default"}      # today's static floor
