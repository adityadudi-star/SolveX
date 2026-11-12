from __future__ import annotations

import asyncio
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.agents.state import STAGES
from app.api.serializers import anomalies_by_metric, audit_dict, metric_dict
from app.database.session import SessionLocal, get_db
from app.models import AuditWorkflow, Company, Filing, MetricResult, WorkflowEvent
from app.schemas import StartAuditRequest
from app.services.report_pdf import render_pdf
from app.services.sec_client import SecError, get_sec_client
from app.workflows.runner import get_runner

router = APIRouter(tags=["companies & audits"])


def _sec_http(e: SecError) -> HTTPException:
    code = {"not_configured": 503, "not_found": 404, "forbidden": 502}.get(e.kind, 502)
    return HTTPException(code, {"error": str(e), "kind": e.kind})


@router.get("/companies/search")
def search_companies(q: str = Query(..., min_length=1, max_length=80)):
    try:
        return {"query": q, "results": get_sec_client().search_companies(q)}
    except SecError as e:
        raise _sec_http(e)


@router.get("/companies/{cik}/filings")
def company_filings(cik: str, include_older: bool = False):
    if not cik.isdigit():
        raise HTTPException(422, "CIK must be numeric")
    try:
        sub, refs = get_sec_client().list_10k_filings(cik, include_older=include_older)
    except SecError as e:
        raise _sec_http(e)
    return {"cik": cik.zfill(10), "name": sub.get("name"), "tickers": sub.get("tickers", []),
            "filings": [{"accession": r.accession, "form": r.form, "filing_date": str(r.filing_date) if r.filing_date else None,
                         "period_end": str(r.report_date) if r.report_date else None, "fiscal_year": r.fiscal_year,
                         "primary_document": r.primary_document, "url": r.url} for r in refs]}


@router.post("/audits/start", status_code=202)
def start_audit(body: StartAuditRequest):
    if not body.accession and not body.fiscal_year:
        raise HTTPException(422, "Provide accession or fiscal_year")
    sec = get_sec_client()
    try:
        sub, refs = sec.list_10k_filings(body.cik, include_older=True)
    except SecError as e:
        raise _sec_http(e)
    ref = next((r for r in refs if (body.accession and r.accession == body.accession)
                or (not body.accession and r.fiscal_year == body.fiscal_year)), None)
    if ref is None:
        raise HTTPException(404, "No matching Form 10-K found on SEC EDGAR for that company / year.")
    tickers = sub.get("tickers") or []
    runner = get_runner()
    wid, created = runner.create_audit(ref, sub.get("name") or body.cik, tickers[0] if tickers else None, force_new=body.force_new)
    if created:
        runner.start_async(wid)
    return {"workflow_id": wid, "created": created,
            "message": "Audit started." if created else "An identical audit is already active; returning it (duplicate request ignored)."}


@router.get("/audits")
def list_audits(status: str | None = None, decision: str | None = None, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    q = db.query(AuditWorkflow)
    if status:
        q = q.filter(AuditWorkflow.status == status)
    if decision:
        q = q.filter(AuditWorkflow.decision == decision)
    return {"audits": [audit_dict(w) for w in q.order_by(AuditWorkflow.started_at.desc()).limit(limit)]}


def _wf_or_404(db: Session, wid: str) -> AuditWorkflow:
    wf = db.get(AuditWorkflow, wid)
    if wf is None:
        raise HTTPException(404, "Audit workflow not found")
    return wf


@router.get("/audits/{workflow_id}")
def get_audit(workflow_id: str, db: Session = Depends(get_db)):
    return audit_dict(_wf_or_404(db, workflow_id), full=True)


def _stage_view(db: Session, wf: AuditWorkflow) -> list[dict]:
    evs = db.query(WorkflowEvent).filter_by(workflow_id=wf.id).order_by(WorkflowEvent.id).all()
    out = []
    for key, label in STAGES:
        st, msg, ts = "pending", "", None
        for e in evs:
            if e.stage != key:
                continue
            st = {"started": "running", "completed": "completed", "skipped": "completed", "paused": "paused", "failed": "failed"}.get(e.status, st)
            if e.status in ("started", "completed", "paused", "failed", "skipped"):
                msg, ts = e.message, e.ts.isoformat()
        if st == "paused" and wf.status != "awaiting_review":
            st = "completed"
        out.append({"stage": key, "label": label, "state": st, "message": msg, "ts": ts})
    return out


@router.get("/audits/{workflow_id}/progress")
async def progress(workflow_id: str, request: Request, after: int = 0, format: str | None = None):
    """Real backend progress events. Server-Sent Events when requested (Accept: text/event-stream), else a JSON snapshot."""
    db = SessionLocal()
    try:
        _wf_or_404(db, workflow_id)
    finally:
        db.close()
    wants_sse = "text/event-stream" in request.headers.get("accept", "") and format != "json"
    if not wants_sse:
        with SessionLocal() as s:
            wf = _wf_or_404(s, workflow_id)
            evs = s.query(WorkflowEvent).filter(WorkflowEvent.workflow_id == workflow_id, WorkflowEvent.id > after).order_by(WorkflowEvent.id).all()
            return {"workflow_id": workflow_id, "status": wf.status, "current_stage": wf.current_stage, "error": wf.error,
                    "stages": _stage_view(s, wf),
                    "events": [{"id": e.id, "stage": e.stage, "status": e.status, "message": e.message, "ts": e.ts.isoformat()} for e in evs]}

    async def gen():
        last = after
        idle_closed = False
        while True:
            if await request.is_disconnected():
                return
            with SessionLocal() as s:
                wf = s.get(AuditWorkflow, workflow_id)
                evs = s.query(WorkflowEvent).filter(WorkflowEvent.workflow_id == workflow_id, WorkflowEvent.id > last).order_by(WorkflowEvent.id).all()
                payload_status = {"status": wf.status, "current_stage": wf.current_stage, "error": wf.error, "stages": _stage_view(s, wf)}
                for e in evs:
                    last = e.id
                    data = {"id": e.id, "stage": e.stage, "event_status": e.status, "message": e.message, "ts": e.ts.isoformat(), **payload_status}
                    yield f"id: {e.id}\nevent: progress\ndata: {json.dumps(data)}\n\n"
                if wf.status in ("completed", "failed", "awaiting_review"):
                    if not evs:
                        yield f"event: end\ndata: {json.dumps(payload_status)}\n\n"
                        return
                    idle_closed = True
            if not idle_closed:
                await asyncio.sleep(0.4)
            else:
                await asyncio.sleep(0.05)
                idle_closed = False

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/audits/{workflow_id}/metrics")
def audit_metrics(workflow_id: str, db: Session = Depends(get_db)):
    wf = _wf_or_404(db, workflow_id)
    ms = db.query(MetricResult).filter_by(workflow_id=workflow_id).order_by(MetricResult.id).all()
    an = anomalies_by_metric(db, [m.id for m in ms])
    return {"workflow_id": workflow_id, "audit": audit_dict(wf), "metrics": [metric_dict(m, an.get(m.id)) for m in ms]}


@router.get("/audits/{workflow_id}/report")
def audit_report(workflow_id: str, format: str = Query("json", pattern="^(json|pdf)$"), db: Session = Depends(get_db)):
    wf = _wf_or_404(db, workflow_id)
    if wf.report is None:
        raise HTTPException(409, "Report not available yet: the audit has not completed (it may be awaiting human review).")
    if format == "pdf":
        return Response(render_pdf(wf.report), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="solvex-audit-{wf.filing.company.ticker or wf.filing.company.cik}-{wf.filing.fiscal_year}.pdf"'})
    return wf.report
