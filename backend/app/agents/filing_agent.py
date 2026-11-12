"""Filing Retrieval Agent + Parsing Agent (deterministic; no LLM)."""
from __future__ import annotations

from app.agents.state import Deps
from app.database.session import session_scope
from app.models import AuditWorkflow
from app.services.sec_client import SecError
from app.workflows.common import get_facts, get_parsed, load_filing_ref, mark_done, stage_guard


@stage_guard("sec_retrieval")
def retrieve(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        wf, filing, ref = load_filing_ref(s, wid)
        cik, url = ref.cik, ref.url
    html = deps.sec.filing_html(ref)            # raises SecError -> visible workflow failure (never fabricated)
    facts = get_facts(deps, cik)
    note = "XBRL Company Facts retrieved." if facts else "XBRL Company Facts unavailable — XBRL verification will report 'unable to match'."
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        wf.stats = {**(wf.stats or {}), "filing_bytes": len(html), "company_facts_available": bool(facts)}
    mark_done(wid, "sec_retrieval", f"Retrieved original filing ({len(html):,} bytes) from {url}. {note}",
              {"url": url, "bytes": len(html), "company_facts": bool(facts)})
    return {}


@stage_guard("parsing")
def parse(deps: Deps, wid: str) -> dict:
    with session_scope() as s:
        _, _, ref = load_filing_ref(s, wid)
    parsed = get_parsed(deps, ref)
    kinds = {k: sum(1 for t in parsed.tables if t.kind == k) for k in ("income", "balance", "cashflow")}
    if not any(kinds.values()):
        raise SecError("The filing was retrieved but no primary financial statement tables could be identified.", kind="parse_failure")
    mark_done(wid, "parsing", f"Parsed {len(parsed.tables)} tables ({kinds}); inline XBRL facts: {parsed.ix_fact_count}.",
              {"tables": len(parsed.tables), "statements": kinds, "inline_xbrl": parsed.is_inline_xbrl, "ix_facts": parsed.ix_fact_count})
    return {}
