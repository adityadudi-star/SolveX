"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StartAuditRequest(BaseModel):
    cik: str = Field(..., pattern=r"^\d{1,10}$", description="SEC CIK (digits)")
    accession: str | None = Field(None, pattern=r"^\d{10}-\d{2}-\d{6}$")
    fiscal_year: int | None = Field(None, ge=1993, le=2100)
    force_new: bool = False

    @field_validator("fiscal_year")
    @classmethod
    def _need_one(cls, v, info):  # noqa: ANN001
        return v


class ReviewActionBody(BaseModel):
    notes: str | None = Field(None, max_length=4000)
    corrected_value: float | None = None


class ThresholdPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_confidence: float | None = None
    review_confidence: float | None = None
    anomaly_mandatory_pct: float | None = None
    anomaly_warning_pct: float | None = None
    accounting_tolerance_pct: float | None = None
    reason: str | None = Field(None, max_length=1000)


class AdaptiveConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_tuning_enabled: float | None = None
    min_reviews: float | None = None
    min_approval_rate: float | None = None
    step: float | None = None
    min_threshold: float | None = None
    max_threshold: float | None = None
    window_width: float | None = None
    cooldown_minutes: float | None = None
    reason: str | None = Field(None, max_length=1000)


class AdaptiveManualSet(BaseModel):
    value: float
    reason: str = Field(..., min_length=3, max_length=1000)


class AdaptiveReason(BaseModel):
    reason: str = Field("", max_length=1000)


class AdaptivePause(BaseModel):
    paused: bool


class SimulateRequest(BaseModel):
    previous_value: float
    current_value: float
    extraction_confidence: float = Field(100, ge=0, le=100)
    accounting_checks_passed: bool = True
    metric: str = "revenue"


class LoginRequest(BaseModel):
    reviewer: str = Field(..., min_length=2, max_length=96)
    token: str


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    database: str
    sec: dict[str, Any]
    llm: dict[str, Any]


class MetricOut(BaseModel):
    id: int
    workflow_id: str
    metric_key: str
    label: str
    statement: str
    found: bool
    value: float | None
    final_value: float | None
    currency: str | None
    unit: str | None
    scale: int | None
    raw_text: str | None
    period_start: str | None
    period_end: str | None
    period_type: str | None
    xbrl_concept: str | None
    confidence: float | None
    validation_status: str
    anomaly_status: str
    xbrl_status: str
    decision: str | None
    escalation_reasons: list[str]
    review_status: str
    evidence_verified: bool
    extraction_method: str | None
    section: str | None
    location: str | None
    source_url: str | None
    company: str | None = None
    ticker: str | None = None
    fiscal_year: int | None = None
    anomaly_pct_change: float | None = None
    anomaly_severity: str | None = None
