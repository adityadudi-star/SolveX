"""End-to-end workflow tests against synthetic SEC fixtures served via a mock transport."""
from __future__ import annotations

import time
from copy import deepcopy

import httpx
import pytest

from app.config import Settings
from app.database.session import session_scope
from app.models import (AnomalyEvent, AuditWorkflow, GroundTruthResult, MetricResult, ModelUsage, ReviewEvent, ValidationCheck, WorkflowEvent)
from app.services.llm import LLMClient
from app.utils.catalog import DECISION_PASSED, DECISION_RECOMMENDED, DECISION_REQUIRED
from tests.conftest import REVIEW_HEADERS
from tests.fixtures import ACC, BASE, CIK, DOC


def metrics(wid) -> dict[str, MetricResult]:
    with session_scope() as s:
        return {m.metric_key: m for m in s.query(MetricResult).filter_by(workflow_id=metric_wid(wid))}


def metric_wid(wid):
    return wid


def wf(wid) -> AuditWorkflow:
    with session_scope() as s:
        w = s.get(AuditWorkflow, wid)
        _ = w.filing.company
        return w


def wait_for(wid, status, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if wf(wid).status == status:
            return
        time.sleep(0.1)
    raise AssertionError(f"workflow {wid} never reached {status}: {wf(wid).status}")


def vals(**over):
    v = deepcopy(BASE)
    for k, x in over.items():
        v[k] = x
    return v


# 1 ---------------------------------------------------------------
def test_normal_audit_fully_passed(env):
    wid = env.audit()
    w = wf(wid)
    assert w.status == "completed" and w.decision == DECISION_PASSED
    ms = metrics(wid)
    assert len(ms) == 9 and all(m.found for m in ms.values())
    assert all(m.decision == DECISION_PASSED and m.confidence == 100.0 and m.xbrl_status == "matched" for m in ms.values())
    rev = ms["revenue"]
    assert rev.value == 1_050_000_000 and rev.currency == "USD" and str(rev.period_end) == "2024-12-31"
    assert rev.source_url.endswith(DOC) and "Total net sales" in rev.snippet and rev.evidence_verified
    assert ms["capital_expenditure"].raw_text == "(60)" and ms["capital_expenditure"].value == 60_000_000   # outflow stored as positive payment
    assert w.report and w.report["decision"] == DECISION_PASSED
    # MD&A decoy table (999,999) was NOT used
    assert all(m.value != 999_999 for m in ms.values())


# 2 ---------------------------------------------------------------
def test_non_blocking_warning_human_consideration(env):
    wid = env.audit(values=vals(revenue=(1300, 1000, 950)))      # +30% : above 25% warning, below 50% mandatory
    ms = metrics(wid)
    assert ms["revenue"].anomaly_status == "warning" and ms["revenue"].decision == DECISION_RECOMMENDED
    assert wf(wid).decision == DECISION_RECOMMENDED
    assert ms["revenue"].review_status == "optional"


def test_borderline_confidence_from_plain_html_table(env):
    """Non-inline HTML, header-year column choice: confidence lands in the 90-98 band => consideration recommended."""
    wid = env.audit(inline=False)
    ms = metrics(wid)
    assert all(m.extraction_method == "html_table" for m in ms.values())
    assert 90 <= ms["revenue"].confidence < 98 and ms["revenue"].decision == DECISION_RECOMMENDED


# 3 ---------------------------------------------------------------
def test_low_confidence_requires_human(env):
    wid = env.audit(inline=False, scale_text=None, facts_status=404)
    m = metrics(wid)["revenue"]
    assert m.confidence < 90 and m.decision == DECISION_REQUIRED and m.review_status == "pending"
    assert wf(wid).status == "awaiting_review"


# 4 ---------------------------------------------------------------
def test_accounting_failure_requires_human(env):
    wid = env.audit(values=vals(total_liabilities=(3500, 2900, 2800)))   # A != L + E ; XBRL agrees, so confidence stays 100
    ms = metrics(wid)
    assert ms["total_liabilities"].confidence == 100.0
    for k in ("total_assets", "total_liabilities", "shareholders_equity"):
        assert ms[k].validation_status == "failed" and ms[k].decision == DECISION_REQUIRED
    with session_scope() as s:
        c = s.query(ValidationCheck).filter_by(workflow_id=wid, check_type="accounting_equation").one()
        assert c.status == "failed" and c.formula and c.inputs["assets"] == 5_000_000_000 and c.tolerance == 0.1


# 5 ---------------------------------------------------------------
def test_confidence_100_with_mandatory_anomaly_still_requires_human(env):
    wid = env.audit(values=vals(revenue=(2500, 1000, 950)))           # +150%
    rev = metrics(wid)["revenue"]
    assert rev.confidence == 100.0 and rev.validation_status == "passed" and rev.xbrl_status == "matched"
    assert rev.anomaly_status == "mandatory" and rev.decision == DECISION_REQUIRED and rev.review_status == "pending"
    with session_scope() as s:
        a = s.query(AnomalyEvent).filter_by(metric_id=rev.id).one()
        assert round(a.pct_change, 1) == 150.0 and a.threshold == 50 and a.previous_value == 1_000_000_000 and a.baseline
    assert wf(wid).status == "awaiting_review"
    ex = env.api().get(f"/api/metrics/{rev.id}/explanation").json()
    assert "unsafe to approve" in ex["ai_explanation"]["text"] and ex["ai_explanation"]["source"] == "template"


# 6 / 7 ------------------------------------------------------------
def test_human_correction_retains_original_and_workflow_resumes_without_repeating(env):
    wid = env.audit(values=vals(revenue=(2500, 1000, 950), net_income=(400, 100, 95)))
    api, fake = env.api(), env.fake
    pend = api.get("/api/reviews/pending").json()["pending"]
    assert {p["metric_key"] for p in pend} == {"revenue", "net_income"}
    sec_before = len(fake.requests)
    started_before = _count_events(wid, "started")
    rid = next(p["id"] for p in pend if p["metric_key"] == "revenue")
    nid = next(p["id"] for p in pend if p["metric_key"] == "net_income")

    # protections & validation
    assert api.post(f"/api/reviews/{rid}/approve").status_code == 401
    assert api.post(f"/api/reviews/{rid}/correct", headers=REVIEW_HEADERS, json={"corrected_value": 1}).status_code == 422   # notes required
    assert api.post(f"/api/reviews/{rid}/reject", headers=REVIEW_HEADERS, json={}).status_code == 422
    assert api.post(f"/api/reviews/{rid}/correct", headers=REVIEW_HEADERS, json={"notes": "x"}).status_code == 422             # value required

    r1 = api.post(f"/api/reviews/{rid}/correct", headers=REVIEW_HEADERS, json={"corrected_value": 1_250_000_000, "notes": "Verified vs press release"})
    assert r1.status_code == 200 and r1.json()["pending_remaining"] == 1 and r1.json()["workflow_resumed"] is False
    assert wf(wid).status == "awaiting_review"            # still paused until ALL mandatory items are resolved
    assert api.post(f"/api/reviews/{rid}/approve", headers=REVIEW_HEADERS, json={}).status_code == 409   # history is append-only

    r2 = api.post(f"/api/reviews/{nid}/approve", headers=REVIEW_HEADERS, json={"notes": "Acquisition gain explained in MD&A"})
    assert r2.json()["workflow_resumed"] is True
    wait_for(wid, "completed")

    ms = metrics(wid)
    assert ms["revenue"].value == 2_500_000_000                      # ORIGINAL preserved
    assert ms["revenue"].final_value == 1_250_000_000 and ms["revenue"].review_status == "corrected"
    assert ms["net_income"].review_status == "approved"
    with session_scope() as s:
        ev = s.query(ReviewEvent).filter_by(metric_id=rid).one()
        assert (ev.original_value, ev.corrected_value, ev.reviewer, ev.action) == (2_500_000_000, 1_250_000_000, "Ada Reviewer", "correct")
        assert ev.notes and ev.ts
    hist = api.get("/api/reviews/history", params={"workflow_id": wid}).json()["history"]
    assert len(hist) == 2

    # resume did not repeat completed work
    assert len(fake.requests) == sec_before, "no SEC calls may be repeated after resume"
    assert _count_events(wid, "started", stage="extraction") == 1
    assert _count_events(wid, "started", stage="sec_retrieval") == 1
    done = wf(wid).completed_stages
    assert len(done) == len(set(done)) and done[-1] == "report"
    assert _count_events(wid, "started") > started_before          # only the remaining stages started
    # report contains the review trail
    rep = api.get(f"/api/audits/{wid}/report").json()
    assert len(rep["review_history"]) == 2 and rep["summary"]["reviewed"]["correct"] == 1


def _count_events(wid, status, stage=None):
    with session_scope() as s:
        q = s.query(WorkflowEvent).filter_by(workflow_id=wid, status=status)
        if stage:
            q = q.filter_by(stage=stage)
        return q.count()


def test_reject_requires_notes_and_excludes_value_after_review(env):
    wid = env.audit(values=vals(revenue=(2500, 1000, 950)))
    api = env.api()
    rid = metrics(wid)["revenue"].id
    r = api.post(f"/api/reviews/{rid}/reject", headers=REVIEW_HEADERS, json={"notes": "Cannot corroborate"})
    assert r.status_code == 200 and r.json()["workflow_resumed"]
    wait_for(wid, "completed")
    m = metrics(wid)["revenue"]
    assert m.review_status == "rejected" and m.value == 2_500_000_000


def test_post_review_revalidation_runs_on_corrected_values(env):
    wid = env.audit(values=vals(total_liabilities=(3500, 2900, 2800)))
    api = env.api()
    ms = metrics(wid)
    api.post(f"/api/reviews/{ms['total_assets'].id}/approve", headers=REVIEW_HEADERS, json={})
    api.post(f"/api/reviews/{ms['shareholders_equity'].id}/approve", headers=REVIEW_HEADERS, json={})
    r = api.post(f"/api/reviews/{ms['total_liabilities'].id}/correct", headers=REVIEW_HEADERS, json={"corrected_value": 3_000_000_000, "notes": "Typo in extraction"})
    assert r.json()["workflow_resumed"]
    wait_for(wid, "completed")
    with session_scope() as s:
        c = s.query(ValidationCheck).filter_by(workflow_id=wid, phase="post_review").one()
        assert c.status == "passed"           # A = 5000 = 3000 (corrected) + 2000
        orig = s.query(ValidationCheck).filter_by(workflow_id=wid, phase="audit", check_type="accounting_equation").one()
        assert orig.status == "failed"        # original failure retained


# 8 ---------------------------------------------------------------
def test_xbrl_mismatch_is_visible(env):
    wid = env.audit(wrong={"revenue": 1049})
    m = metrics(wid)["revenue"]
    assert m.xbrl_status == "mismatched" and m.decision == DECISION_REQUIRED
    with session_scope() as s:
        g = s.query(GroundTruthResult).filter_by(metric_id=m.id).one()
        assert g.status == "mismatched" and g.xbrl_value == 1_049_000_000 and g.extracted_value == 1_050_000_000 and g.difference == 1_000_000
    x = wf(wid).summary["xbrl"]
    assert x["mismatched"] == 1 and x["matched"] == 8 and "No accuracy percentage is claimed" in x["methodology"]


def test_xbrl_missing_concept_is_reported_missing(env):
    wid = env.audit(drop={"capital_expenditure"})
    m = metrics(wid)["capital_expenditure"]
    assert m.xbrl_status == "missing" and m.decision == DECISION_RECOMMENDED


# 9 ---------------------------------------------------------------
def test_missing_history_is_insufficient_history(env):
    wid = env.audit(history=False)
    rev = metrics(wid)["revenue"]
    assert rev.anomaly_status == "insufficient_history" and rev.decision == DECISION_RECOMMENDED
    with session_scope() as s:
        assert "Insufficient History" in s.query(AnomalyEvent).filter_by(metric_id=rev.id).one().explanation


# 10 --------------------------------------------------------------
def test_sec_failure_is_visible_and_nothing_is_fabricated(env):
    wid = env.audit(fail_html=503)
    w = wf(wid)
    assert w.status == "failed" and "SEC request failed" in w.error
    with session_scope() as s:
        assert s.query(MetricResult).filter_by(workflow_id=wid).count() == 0
        assert s.query(WorkflowEvent).filter_by(workflow_id=wid, status="failed").count() >= 1
    assert env.fake.count(DOC) == 3          # 1 try + 2 retries (exponential backoff), then give up


def test_sec_not_configured_fails_loudly(env):
    env.use()
    env.runner.deps.sec.s = Settings(sec_contact_email="", cache_dir=str(env.tmp / "c2"))
    wid, _ = env.runner.create_audit(env.ref, "Testco Inc", "TSTC", force_new=True)
    env.runner.run(wid)
    assert wf(wid).status == "failed" and "SEC_CONTACT_EMAIL" in wf(wid).error


def test_sec_cache_avoids_repeat_downloads(env):
    env.audit()
    n = env.fake.count(DOC)
    env.runner.create_audit(env.ref, "Testco Inc", "TSTC", force_new=True)
    from app.workflows.common import clear_caches
    clear_caches()
    env.runner.deps.sec.filing_html(env.ref)
    assert env.fake.count(DOC) == n == 1


# restatement / duplicates / recovery -------------------------------
def test_restatement_is_identified(env):
    wid = env.audit(restate_prior={"revenue": 990})   # originally reported 990, comparative now 1000
    rev = metrics(wid)["revenue"]
    with session_scope() as s:
        c = s.query(ValidationCheck).filter_by(workflow_id=wid, check_type="restatement", metric_id=rev.id).one()
        assert c.status == "warning" and c.result["originally_reported"] == 990_000_000
    assert rev.decision == DECISION_RECOMMENDED


def test_duplicate_requests_return_existing_active_audit(env):
    env.use(values=vals(revenue=(2500, 1000, 950)))
    api = env.api()
    r1 = api.post("/api/audits/start", json={"cik": CIK, "accession": ACC})
    assert r1.status_code == 202 and r1.json()["created"] is True
    wid = r1.json()["workflow_id"]
    wait_for(wid, "awaiting_review")
    r2 = api.post("/api/audits/start", json={"cik": CIK, "accession": ACC})
    assert r2.json()["workflow_id"] == wid and r2.json()["created"] is False
    assert api.post("/api/audits/start", json={"cik": CIK}).status_code == 422
    assert api.post("/api/audits/start", json={"cik": "abc", "accession": ACC}).status_code == 422


def test_checkpoint_recovery_after_crash_does_not_repeat_completed_stages(env, monkeypatch):
    import app.agents.graph as g
    env.use()
    real = list(g.NODES)

    def crash(deps, wid):
        raise RuntimeError("simulated process crash")
    monkeypatch.setattr(g, "NODES", [(n, crash if n == "anomaly" else f) for n, f in real])
    from app.workflows.runner import WorkflowRunner
    r1 = WorkflowRunner(env.runner.deps, checkpoint_path=str(env.tmp / "cp.db"))
    wid, _ = r1.create_audit(env.ref, "Testco Inc", "TSTC", force_new=True)
    r1.run(wid)
    assert wf(wid).status == "failed"
    done_before = list(wf(wid).completed_stages)
    assert done_before[-1] == "validation"
    # "restart": new runner/process, healthy code; mark workflow as it would be after a hard crash
    with session_scope() as s:
        w = s.get(AuditWorkflow, wid)
        w.status, w.error = "running", None
    monkeypatch.setattr(g, "NODES", real)
    reqs = len(env.fake.requests)
    r2 = WorkflowRunner(env.runner.deps, checkpoint_path=str(env.tmp / "cp.db"))
    r2.recover(wid)
    assert wf(wid).status == "completed" and wf(wid).decision == DECISION_PASSED
    assert len(env.fake.requests) == reqs
    for st in done_before:
        assert _count_events(wid, "started", stage=st) == 1, f"{st} was repeated after recovery"


# API surface -------------------------------------------------------
def test_api_surface_and_exports(env):
    wid = env.audit(values=vals(revenue=(2500, 1000, 950)))
    api = env.api()
    assert api.get("/api/health").json()["sec"]["configured"] in (True, False)
    s = api.get("/api/companies/search", params={"q": "tstc"}).json()["results"]
    assert s[0]["cik"] == CIK
    f = api.get(f"/api/companies/{CIK}/filings").json()["filings"]
    assert [x["form"] for x in f] == ["10-K", "10-K"]                       # 10-Q excluded
    prog = api.get(f"/api/audits/{wid}/progress").json()
    assert prog["status"] == "awaiting_review" and [s["state"] for s in prog["stages"]][:10] == ["completed"] * 10
    assert next(s for s in prog["stages"] if s["stage"] == "human_review")["state"] == "paused"
    m = api.get(f"/api/audits/{wid}/metrics").json()["metrics"]
    assert len(m) == 9 and all("confidence" in x and "xbrl_status" in x and "decision" in x for x in m)
    mid = next(x["id"] for x in m if x["metric_key"] == "revenue")
    ev = api.get(f"/api/metrics/{mid}/evidence").json()
    assert ev["observed_facts"]["source_url"].endswith(DOC) and ev["confidence"]["signals"] and ev["historical_comparison"]["anomaly"]["mandatory"]
    assert api.get(f"/api/audits/{wid}/report").status_code == 409         # not complete while awaiting review
    summ = api.get("/api/analytics/summary").json()
    assert summ["pending_reviews"] == 1 and summ["audits_by_decision"][DECISION_REQUIRED] == 1 and summ["metrics_extracted"] == 9
    tr = api.get("/api/analytics/trends", params={"cik": CIK}).json()
    pts = tr["series"]["revenue"]["points"]
    assert [p["year"] for p in pts] == [2022, 2023, 2024] and pts[-1]["pct_change"] == 150.0 and pts[-1]["mandatory_level"]
    assert api.get("/api/analytics/trends", params={"cik": "9999"}).status_code == 404
    api.post(f"/api/reviews/{mid}/approve", headers=REVIEW_HEADERS, json={"notes": "ok"})
    wait_for(wid, "completed")
    pdf = api.get(f"/api/audits/{wid}/report", params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert api.get("/api/observability/usage").json()["llm"]["enabled"] is False
    assert api.get("/api/audits", params={"status": "completed"}).json()["audits"][0]["workflow_id"] == wid


def test_sse_progress_stream(env):
    wid = env.audit()
    with env.api().stream("GET", f"/api/audits/{wid}/progress", headers={"Accept": "text/event-stream"}) as r:
        body = "".join(r.iter_text())
    assert "event: progress" in body and "event: end" in body and '"stage": "sec_retrieval"' in body


def test_settings_api_guard_rails(env):
    env.use()
    api = env.api()
    assert api.patch("/api/settings/thresholds", json={"approval_confidence": 99}).status_code == 401
    assert api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"approval_confidence": 50}).status_code == 422
    assert api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"bypass_review": 1}).status_code == 422
    ok = api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"anomaly_mandatory_pct": 40, "reason": "stricter"})
    assert ok.status_code == 200
    st = api.get("/api/settings").json()
    assert st["thresholds"]["anomaly_mandatory_pct"] == 40 and st["changes"][0]["by"] == "Ada Reviewer" and st["changes"][0]["old"] == 50


def test_threshold_change_applies_to_new_audits_and_is_snapshotted(env):
    env.use()
    api = env.api()
    api.patch("/api/settings/thresholds", headers=REVIEW_HEADERS, json={"anomaly_warning_pct": 6, "anomaly_mandatory_pct": 10})
    wid = env.audit(values=vals(revenue=(1070, 1000, 950)))     # +7%  -> above new 6% warning
    assert metrics(wid)["revenue"].anomaly_status == "warning"
    assert wf(wid).thresholds["anomaly_mandatory_pct"] == 10


def test_decision_simulator_critical_case(env):
    env.use()
    r = env.api().post("/api/decision/simulate", json={"previous_value": 200e6, "current_value": 500e6, "extraction_confidence": 100}).json()
    assert r["decision"] == DECISION_REQUIRED and r["anomaly"]["pct_change"] == 150.0 and r["llm_involved"] is False and r["simulation"] is True
    assert "unsafe to approve" in r["lesson"]


# LLM is optional, tracked, and can never change decisions -------------
def test_llm_explanations_are_tracked_and_cannot_change_decisions(env):
    env.use(values=vals(revenue=(2500, 1000, 950)))
    cfg = Settings(sec_contact_email="qa@solvex-test.invalid", llm_provider="openai", llm_api_key="test-key", llm_model="test-model",
                   llm_base_url="http://llm.invalid/v1", llm_input_cost_per_mtok=1.0, llm_output_cost_per_mtok=2.0, llm_max_retries=0)

    def handler(req: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "Revenue approved automatically, no review needed."}}],
                                         "usage": {"prompt_tokens": 120, "completion_tokens": 30}})
    env.runner.deps.llm = LLMClient(cfg, transport=httpx.MockTransport(handler))
    wid, _ = env.runner.create_audit(env.ref, "Testco Inc", "TSTC", force_new=True)
    env.runner.run(wid)
    rev = metrics(wid)["revenue"]
    assert rev.decision == DECISION_REQUIRED and rev.review_status == "pending"        # LLM text did not override
    ex = env.api().get(f"/api/metrics/{rev.id}/explanation").json()
    assert ex["ai_explanation"]["source"] == "llm" and ex["ai_explanation"]["model"] == "test-model"
    assert ex["observed_facts"]["extracted_value"] == 2_500_000_000                    # facts separated from AI text
    with session_scope() as s:
        u = s.query(ModelUsage).first()
        assert u.input_tokens == 120 and u.output_tokens == 30 and u.cost_usd == pytest.approx(120e-6 + 60e-6) and u.purpose == "explanation"
        assert s.query(ModelUsage).count() == 1       # only the non-passed metric used tokens (token-efficient)
