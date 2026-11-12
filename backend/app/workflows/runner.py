"""Workflow runner: creates audits (idempotently), executes the LangGraph, resumes after human review, recovers after crashes."""
from __future__ import annotations

import sqlite3
import threading
import traceback
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agents.graph import build_graph
from app.agents.state import STAGE_LABELS, Deps
from app.config import get_settings
from app.database.session import session_scope
from app.models import AuditWorkflow, Company, Filing, MetricResult
from app.models.entities import utcnow
from app.services.llm import get_llm
from app.services.sec_client import FilingRef, SecError, current_stats, get_sec_client
from app.services.settings_service import get_thresholds
from app.workflows.common import emit

ACTIVE_STATUSES = ("running", "awaiting_review")


class WorkflowRunner:
    def __init__(self, deps: Deps | None = None, checkpoint_path: str | None = None):
        self.deps = deps or Deps(sec=get_sec_client(), llm=get_llm())
        self.checkpoint_path = checkpoint_path or get_settings().checkpoint_db_path
        self._graph = None
        self._graph_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ---------------------------------------------------------------- graph / checkpoints
    @property
    def graph(self):
        with self._graph_lock:
            if self._graph is None:
                if self.checkpoint_path != ":memory:":
                    Path(self.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.checkpoint_path, check_same_thread=False)
                self._graph = build_graph(self.deps, SqliteSaver(conn))
            return self._graph

    def _lock(self, wid: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(wid, threading.Lock())

    # ---------------------------------------------------------------- creation (idempotent)
    def create_audit(self, ref: FilingRef, company_name: str, ticker: str | None, force_new: bool = False) -> tuple[str, bool]:
        """Returns (workflow_id, created). Duplicate requests for the same filing return the existing workflow."""
        with session_scope() as s:
            comp = s.query(Company).filter_by(cik=ref.cik).first()
            if comp is None:
                comp = Company(cik=ref.cik, name=company_name, ticker=ticker)
                s.add(comp)
                s.flush()
            filing = s.query(Filing).filter_by(company_id=comp.id, accession=ref.accession).first()
            if filing is None:
                filing = Filing(company_id=comp.id, accession=ref.accession, form=ref.form, filing_date=ref.filing_date,
                                report_date=ref.report_date, fiscal_year=ref.fiscal_year, primary_document=ref.primary_document, url=ref.url)
                s.add(filing)
                s.flush()
            if not force_new:
                existing = (s.query(AuditWorkflow).filter(AuditWorkflow.filing_id == filing.id, AuditWorkflow.status.in_(ACTIVE_STATUSES))
                            .order_by(AuditWorkflow.started_at.desc()).first())
                if existing:
                    return existing.id, False
            wf = AuditWorkflow(filing_id=filing.id, status="running", current_stage="queued", completed_stages=[],
                               thresholds=get_thresholds(s), summary={}, stats={})
            s.add(wf)
            s.flush()
            wid = wf.id
        emit(wid, "queued", "info", "Audit queued.")
        return wid, True

    # ---------------------------------------------------------------- execution
    def _invoke(self, wid: str, payload) -> None:
        cfg = {"configurable": {"thread_id": wid}}
        stats: dict = {}
        tok = current_stats.set(stats)
        try:
            with self._lock(wid):
                self.graph.invoke(payload, cfg)
        except Exception as e:  # noqa: BLE001
            self._fail(wid, e)
        finally:
            current_stats.reset(tok)
            self._merge_stats(wid, stats)

    def _merge_stats(self, wid: str, stats: dict) -> None:
        if not stats:
            return
        with session_scope() as s:
            wf = s.get(AuditWorkflow, wid)
            if wf:
                cur = dict(wf.stats or {})
                for k, v in stats.items():
                    cur[k] = cur.get(k, 0) + v
                wf.stats = cur

    def _fail(self, wid: str, e: Exception) -> None:
        msg = f"{type(e).__name__}: {e}"
        kind = e.kind if isinstance(e, SecError) else "internal_error"
        with session_scope() as s:
            wf = s.get(AuditWorkflow, wid)
            if wf:
                wf.status, wf.error, wf.finished_at = "failed", msg, utcnow()
                wf.duration_ms = int((wf.finished_at - wf.started_at).total_seconds() * 1000)
        emit(wid, "workflow", "failed", f"Audit failed — no results were fabricated. {msg}", {"kind": kind, "trace": traceback.format_exc()[-1500:]})

    def run(self, wid: str) -> None:
        self._invoke(wid, {"workflow_id": wid})

    def resume(self, wid: str) -> None:
        """Resume the paused graph from its saved checkpoint (completed stages are NOT re-executed)."""
        emit(wid, "human_review", "info", "All mandatory reviews resolved — resuming workflow from the saved checkpoint.")
        self._invoke(wid, Command(resume={"reviews_resolved": True}))

    def recover(self, wid: str) -> None:
        """Continue an interrupted (crashed) run from its last checkpoint."""
        emit(wid, "workflow", "info", "Recovering from last saved checkpoint.")
        self._invoke(wid, None)

    # ---------------------------------------------------------------- background helpers
    def submit(self, fn, wid: str) -> threading.Thread:
        t = threading.Thread(target=fn, args=(wid,), name=f"solvex-{wid[:6]}", daemon=True)
        t.start()
        return t

    def start_async(self, wid: str) -> None:
        self.submit(self.run, wid)

    def resume_async(self, wid: str) -> None:
        self.submit(self.resume, wid)

    def recover_incomplete(self) -> list[str]:
        """On startup: continue workflows that were running when the process stopped; resume fully-reviewed paused ones."""
        ids: list[str] = []
        with session_scope() as s:
            for wf in s.query(AuditWorkflow).filter(AuditWorkflow.status.in_(ACTIVE_STATUSES)).all():
                pending = s.query(MetricResult).filter_by(workflow_id=wf.id, review_status="pending").count()
                if wf.status == "running":
                    ids.append(("recover", wf.id))
                elif pending == 0:
                    ids.append(("resume", wf.id))
        for kind, wid in ids:
            self.submit(self.recover if kind == "recover" else self.resume, wid)
        return [w for _, w in ids]


_runner: WorkflowRunner | None = None


def get_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        _runner = WorkflowRunner()
    return _runner


def set_runner(r: WorkflowRunner | None) -> None:
    global _runner
    _runner = r
