from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return uuid.uuid4().hex


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    filings: Mapped[list["Filing"]] = relationship(back_populates="company")


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("company_id", "accession"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    accession: Mapped[str] = mapped_column(String(32), index=True)
    form: Mapped[str] = mapped_column(String(16))
    filing_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)  # period of report (fiscal year end)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True)
    primary_document: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(512))
    company: Mapped[Company] = relationship(back_populates="filings")
    workflows: Mapped[list["AuditWorkflow"]] = relationship(back_populates="filing")


class AuditWorkflow(Base):
    __tablename__ = "audit_workflows"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)  # workflow_id / LangGraph thread_id
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)  # running|awaiting_review|completed|failed
    current_stage: Mapped[str] = mapped_column(String(48), default="queued")
    completed_stages: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision: Mapped[str | None] = mapped_column(String(48), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # snapshot used for this audit
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # sec requests, retries, cache hits
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    filing: Mapped[Filing] = relationship(back_populates="workflows")
    metrics: Mapped[list["MetricResult"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")
    events: Mapped[list["WorkflowEvent"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")


class WorkflowEvent(Base):
    """Durable progress events (drive the SSE stream; also the workflow audit trail)."""
    __tablename__ = "workflow_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    stage: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16))  # started|completed|failed|info|paused|skipped
    message: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    workflow: Mapped[AuditWorkflow] = relationship(back_populates="events")


class MetricResult(Base):
    __tablename__ = "metric_results"
    __table_args__ = (UniqueConstraint("workflow_id", "metric_key"), Index("ix_metric_decision", "decision"))
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(48))
    label: Mapped[str] = mapped_column(String(96))
    statement: Mapped[str] = mapped_column(String(24))
    found: Mapped[bool] = mapped_column(Boolean, default=True)  # False => missing (never treated as zero)
    value: Mapped[float | None] = mapped_column(Float)  # ORIGINAL extracted value; never overwritten
    currency: Mapped[str | None] = mapped_column(String(8))
    unit: Mapped[str | None] = mapped_column(String(32))  # e.g. "USD (millions as displayed)"
    scale: Mapped[int | None] = mapped_column(Integer)  # multiplier exponent as displayed: 0, 3, 6, 9
    raw_text: Mapped[str | None] = mapped_column(String(64))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    period_type: Mapped[str | None] = mapped_column(String(12))  # duration|instant
    xbrl_concept: Mapped[str | None] = mapped_column(String(160))
    section: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(255))
    snippet: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(512))
    extraction_method: Mapped[str | None] = mapped_column(String(48))
    extraction_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    confidence_signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    validation_status: Mapped[str] = mapped_column(String(16), default="pending")  # passed|warning|failed|pending
    anomaly_status: Mapped[str] = mapped_column(String(24), default="pending")  # normal|warning|mandatory|insufficient_history
    xbrl_status: Mapped[str] = mapped_column(String(16), default="pending")  # matched|mismatched|missing|unable
    decision: Mapped[str | None] = mapped_column(String(48), index=True)
    escalation_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(16), default="not_required", index=True)
    # not_required | optional | pending | approved | corrected | rejected
    final_value: Mapped[float | None] = mapped_column(Float)  # reviewer-resolved value (original stays in `value`)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    workflow: Mapped[AuditWorkflow] = relationship(back_populates="metrics")
    checks: Mapped[list["ValidationCheck"]] = relationship(back_populates="metric")
    anomalies: Mapped[list["AnomalyEvent"]] = relationship(back_populates="metric")
    reviews: Mapped[list["ReviewEvent"]] = relationship(back_populates="metric", order_by="ReviewEvent.id")
    ground_truth: Mapped[list["GroundTruthResult"]] = relationship(back_populates="metric")


class ValidationCheck(Base):
    __tablename__ = "validation_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("metric_results.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(160))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    formula: Mapped[str] = mapped_column(String(255), default="")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tolerance: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))  # passed|warning|failed|skipped
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    metric_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    phase: Mapped[str] = mapped_column(String(16), default="audit")  # audit | post_review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    metric: Mapped[MetricResult | None] = relationship(back_populates="checks")


class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("metric_results.id"), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    baseline: Mapped[float | None] = mapped_column(Float)
    current_value: Mapped[float | None] = mapped_column(Float)
    previous_value: Mapped[float | None] = mapped_column(Float)
    abs_change: Mapped[float | None] = mapped_column(Float)
    pct_change: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(12))  # none|low|moderate|high
    status: Mapped[str] = mapped_column(String(24))  # normal|warning|mandatory|insufficient_history
    mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    metric: Mapped[MetricResult | None] = relationship(back_populates="anomalies")


class ReviewEvent(Base):
    """APPEND-ONLY human review history. Updates/deletes are rejected at the ORM level."""
    __tablename__ = "review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_results.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    action: Mapped[str] = mapped_column(String(12))  # approve|correct|reject
    reviewer: Mapped[str] = mapped_column(String(96))
    original_value: Mapped[float | None] = mapped_column(Float)
    corrected_value: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    previous_review_status: Mapped[str] = mapped_column(String(16))
    new_review_status: Mapped[str] = mapped_column(String(16))
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    metric: Mapped[MetricResult] = relationship(back_populates="reviews")


class GroundTruthResult(Base):
    __tablename__ = "ground_truth_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    metric_id: Mapped[int] = mapped_column(ForeignKey("metric_results.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))  # matched|mismatched|missing|unable
    xbrl_concept: Mapped[str | None] = mapped_column(String(160))
    xbrl_value: Mapped[float | None] = mapped_column(Float)
    extracted_value: Mapped[float | None] = mapped_column(Float)
    difference: Mapped[float | None] = mapped_column(Float)
    tolerance: Mapped[float | None] = mapped_column(Float)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    unit: Mapped[str | None] = mapped_column(String(16))
    accession: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    metric: Mapped[MetricResult] = relationship(back_populates="ground_truth")


class ModelUsage(Base):
    __tablename__ = "model_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("audit_workflows.id"), index=True)
    provider: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(96))
    purpose: Mapped[str] = mapped_column(String(48))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ThresholdChange(Base):
    """APPEND-ONLY record of threshold changes."""
    __tablename__ = "threshold_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48), index=True)
    old_value: Mapped[float] = mapped_column(Float)
    new_value: Mapped[float] = mapped_column(Float)
    changed_by: Mapped[str] = mapped_column(String(96))
    reason: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppendOnlyError(RuntimeError):
    pass


def _block(_mapper, _conn, target):  # noqa: ANN001
    raise AppendOnlyError(f"{type(target).__name__} is append-only: updates and deletes are not permitted")


for _cls in (ReviewEvent, ThresholdChange):
    event.listen(_cls, "before_update", _block)
    event.listen(_cls, "before_delete", _block)
