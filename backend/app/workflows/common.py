"""Shared workflow helpers: durable events, stage guards (idempotency), in-process caches."""
from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agents.state import STAGE_LABELS, Deps
from app.database.session import session_scope
from app.models import AuditWorkflow, Filing, WorkflowEvent
from app.models.entities import utcnow
from app.services.filing_parser import ParsedFiling, parse_filing
from app.services.sec_client import FilingRef


def emit(wid: str, stage: str, status: str, message: str = "", detail: dict[str, Any] | None = None) -> None:
    with session_scope() as s:
        s.add(WorkflowEvent(workflow_id=wid, stage=stage, status=status, message=message, detail=detail or {}, ts=utcnow()))
        wf = s.get(AuditWorkflow, wid)
        if wf is not None and status in ("started", "paused"):
            wf.current_stage = stage


def stage_done(wid: str, stage: str) -> bool:
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        return bool(wf and stage in (wf.completed_stages or []))


def mark_done(wid: str, stage: str, message: str = "", detail: dict[str, Any] | None = None) -> None:
    with session_scope() as s:
        wf = s.get(AuditWorkflow, wid)
        if wf is not None:
            done = list(wf.completed_stages or [])
            if stage not in done:
                done.append(stage)
            wf.completed_stages = done
        s.add(WorkflowEvent(workflow_id=wid, stage=stage, status="completed", message=message, detail=detail or {}, ts=utcnow()))


def skipped(wid: str, stage: str) -> None:
    emit(wid, stage, "skipped", f"{STAGE_LABELS.get(stage, stage)} already completed — reused saved checkpoint data (no repeated work).")


def stage_guard(stage: str):
    """Decorator: skip a node if its stage is already complete (idempotent re-entry after resume/recovery)."""
    def deco(fn: Callable[[Deps, str], dict]):
        def wrapper(deps: Deps, wid: str) -> dict:
            if stage_done(wid, stage):
                skipped(wid, stage)
                return {}
            emit(wid, stage, "started", f"{STAGE_LABELS.get(stage, stage)} started")
            try:
                out = fn(deps, wid)
            except Exception as e:  # noqa: BLE001
                emit(wid, stage, "failed", f"{type(e).__name__}: {e}")
                raise
            return out or {}
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


def load_filing_ref(s: Session, wid: str) -> tuple[AuditWorkflow, Filing, FilingRef]:
    wf = s.get(AuditWorkflow, wid)
    assert wf is not None
    f = wf.filing
    ref = FilingRef(accession=f.accession, form=f.form, filing_date=f.filing_date, report_date=f.report_date,
                    primary_document=f.primary_document, cik=f.company.cik)
    return wf, f, ref


# ---- bounded in-process caches (rebuilt from the on-disk SEC cache after a restart; never re-download if cached)
class _LRU:
    def __init__(self, n: int):
        self.n, self.d, self.lock = n, OrderedDict(), threading.Lock()

    def get_or_make(self, key, make):
        with self.lock:
            if key in self.d:
                self.d.move_to_end(key)
                return self.d[key]
        val = make()
        with self.lock:
            self.d[key] = val
            while len(self.d) > self.n:
                self.d.popitem(last=False)
        return val

    def clear(self):
        with self.lock:
            self.d.clear()


_parsed_cache = _LRU(2)
_facts_cache = _LRU(4)


def clear_caches() -> None:
    _parsed_cache.clear()
    _facts_cache.clear()


def get_parsed(deps: Deps, ref: FilingRef) -> ParsedFiling:
    return _parsed_cache.get_or_make(ref.accession, lambda: parse_filing(deps.sec.filing_html(ref)))


def get_facts(deps: Deps, cik: str) -> dict | None:
    """Company Facts or None if SEC has none / unreachable (verification then reports 'unable', never fabricates)."""
    from app.services.sec_client import SecError
    try:
        return _facts_cache.get_or_make(cik, lambda: deps.sec.company_facts(cik))
    except SecError:
        return None


def now() -> datetime:
    return utcnow()
