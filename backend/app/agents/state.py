from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from app.services.llm import LLMClient
from app.services.sec_client import SecClient


class AuditState(TypedDict, total=False):
    """Small, serialisable LangGraph state. Heavy data (metrics, evidence, checks) lives in the database;
    the checkpoint only needs to know which workflow it belongs to and the routing facts."""
    workflow_id: str
    decision: str
    needs_review: bool
    error: str


@dataclass
class Deps:
    sec: SecClient
    llm: LLMClient


# Ordered stages shown in the UI. Names match LangGraph node names.
STAGES: list[tuple[str, str]] = [
    ("sec_retrieval", "SEC filing retrieval"),
    ("parsing", "Document parsing"),
    ("extraction", "Financial extraction"),
    ("confidence", "Confidence calculation"),
    ("validation", "Accounting validation"),
    ("anomaly", "Anomaly investigation"),
    ("xbrl_verification", "XBRL verification"),
    ("decision", "Audit decision"),
    ("explainability", "Evidence & explanation"),
    ("review_preparation", "Human review preparation"),
    ("human_review", "Human review"),
    ("post_review", "Post-review revalidation"),
    ("report", "Report generation"),
]
STAGE_LABELS = dict(STAGES)
