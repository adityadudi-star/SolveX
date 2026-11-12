"""SolveX Financial Auditor — FastAPI application."""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audits, metrics, system
from app.config import APP_DESCRIPTION, APP_NAME, APP_TAGLINE, APP_VERSION, get_settings
from app.database.migrate import ensure_schema
from app.database.session import init_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    ensure_schema()   # Alembic migrations (backend/alembic) are the source of truth for the schema
    from app.workflows.runner import get_runner
    threading.Thread(target=lambda: get_runner().recover_incomplete(), daemon=True).start()   # checkpoint recovery
    yield


app = FastAPI(
    title=f"{APP_NAME} API", version=APP_VERSION, lifespan=lifespan,
    description=f"**SolveX** — {APP_TAGLINE}\n\n{APP_DESCRIPTION}\n\nSEC EDGAR → extraction → XBRL verification → accounting validation → "
                "anomaly investigation → evidence-based confidence → mandatory human review (LangGraph, persistent checkpoints). "
                "Reviewer endpoints use demo shared-token protection (not production-grade).",
    contact={"name": "SolveX"},
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_methods=["*"], allow_headers=["*"])
for r in (system.router, audits.router, metrics.router):
    app.include_router(r, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    return {"name": APP_NAME, "tagline": APP_TAGLINE, "docs": "/docs", "health": "/api/health"}
