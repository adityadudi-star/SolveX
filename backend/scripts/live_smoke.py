"""Live SEC smoke test: runs a REAL audit against SEC EDGAR using a throwaway database (your real data is untouched).

Prerequisite: SEC_CONTACT_EMAIL set in backend/.env (SEC fair-access policy).

    cd backend
    .venv\\Scripts\\python scripts\\live_smoke.py AAPL          # latest 10-K
    .venv\\Scripts\\python scripts\\live_smoke.py NVDA 2025     # specific fiscal year

Prints every extracted metric with confidence, XBRL status and the decision, so extraction quality on real filings can be inspected.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tmp = Path(tempfile.mkdtemp(prefix="solvex_live_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(tmp / 'smoke.db').as_posix()}"
os.environ["CHECKPOINT_DB_PATH"] = str(tmp / "cp.db")

from app.config import get_settings  # noqa: E402
from app.database.session import create_all, init_engine, session_scope  # noqa: E402
from app.models import AuditWorkflow, MetricResult, WorkflowEvent  # noqa: E402
from app.services.sec_client import SecError, get_sec_client  # noqa: E402
from app.workflows.runner import WorkflowRunner  # noqa: E402


def main() -> int:
    if not get_settings().sec_configured:
        print("SEC_CONTACT_EMAIL is not set in backend/.env — SEC requires a real contact email. Aborting (nothing fabricated).")
        return 2
    query = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    init_engine()
    create_all()
    sec = get_sec_client()
    try:
        hits = sec.search_companies(query)
        if not hits:
            print(f"No SEC registrant matches {query!r}")
            return 1
        co = hits[0]
        _, refs = sec.list_10k_filings(co["cik"], include_older=year is not None)
        ref = next((r for r in refs if year is None or r.fiscal_year == year), None)
        if ref is None:
            print(f"No 10-K found for {co['name']} FY{year}")
            return 1
    except SecError as e:
        print("SEC error:", e)
        return 1
    print(f"Auditing {co['name']} ({co['ticker']}) CIK {co['cik']} — 10-K FY{ref.fiscal_year}, period {ref.report_date}\n  {ref.url}\n")
    runner = WorkflowRunner(checkpoint_path=str(tmp / "cp.db"))
    wid, _ = runner.create_audit(ref, co["name"], co["ticker"], force_new=True)
    runner.run(wid)
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        print(f"status={wf.status} decision={wf.decision} error={wf.error}")
        for e in s.query(WorkflowEvent).filter_by(workflow_id=wid).order_by(WorkflowEvent.id):
            if e.status in ("completed", "failed", "paused"):
                print(f"  [{e.stage}] {e.message[:140]}")
        print(f"\n{'metric':24} {'value (USD)':>20} {'conf':>6} {'xbrl':>10} {'anomaly':>20} decision")
        for m in s.query(MetricResult).filter_by(workflow_id=wid).order_by(MetricResult.id):
            v = f"{m.value:,.0f}" if m.value is not None else "MISSING"
            print(f"{m.label:24} {v:>20} {m.confidence or 0:>6.1f} {m.xbrl_status:>10} {m.anomaly_status:>20} {m.decision}")
    print(f"\n(throwaway DB: {tmp})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
