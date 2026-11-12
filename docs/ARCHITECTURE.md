# SolveX Financial Auditor — Architecture

> **Note:** the build brief referenced a PRD in `docs/`; none was present in the working directory when the project was created, so this
> document and the README were derived from the build brief itself. Drop the PRD here and reconcile any differences.

## Workflow (LangGraph, persistent checkpoints)

```
sec_retrieval → parsing → extraction → confidence → validation → anomaly → xbrl_verification
   → decision → explainability → review_preparation → human_review ⏸ → post_review → report
```

| Stage | Module | Notes |
|---|---|---|
| `sec_retrieval` | `agents/filing_agent.py` | Original filing HTML + XBRL Company Facts via `services/sec_client.py` (cached, rate-limited, backoff). Failure ⇒ visible workflow failure, nothing fabricated. |
| `parsing` | `services/filing_parser.py` | lxml tables, inline-XBRL contexts/facts, header years, unit scale, statement classification. |
| `extraction` | `services/extraction_service.py` | Label→concept mapping (`utils/catalog.py`); column chosen by iXBRL context → header year → position. Optional LLM *row selection* only when deterministic mapping fails. Evidence re-verified. XBRL match computed. |
| `confidence` | `services/confidence.py` | 7 weighted signals, all stored. |
| `validation` | `services/validation_service.py` | Accounting equation, missing data, unit/period consistency, sign, scaling, restatement, segment (skipped honestly). |
| `anomaly` | `services/anomaly_service.py` | YoY % vs configurable thresholds; baseline = mean of ≤3 prior years. |
| `xbrl_verification` | `agents/xbrl_agent.py` | Persists matched / mismatched / missing / unable; honest match counts + methodology. |
| `decision` | `services/decision_service.py` | Pure Python, three levels, highest severity wins. **No LLM input exists.** |
| `explainability` | `agents/explanation_agent.py` | Runs *before* the pause so reviewers see it. Observed facts / deterministic calculations / AI text are stored separately. |
| `human_review` | `agents/decision_agent.py` | `langgraph.types.interrupt` — checkpoint saved, workflow `awaiting_review`. |
| `post_review` | `agents/decision_agent.py` | Re-runs the accounting equation on reviewer-resolved values (originals retained). |
| `report` | `agents/report_agent.py` | Stored JSON report, PDF export via reportlab. |

### Idempotency & resume
* Every node is wrapped by `workflows/common.stage_guard`: a stage already in `AuditWorkflow.completed_stages` is skipped (event `skipped`).
* LangGraph `SqliteSaver` (`checkpoints.db`) holds graph state; the application DB holds all business data (metrics, evidence, checks, anomalies).
* Review → when the last *pending* metric of a workflow is resolved, `Command(resume=…)` continues from the saved checkpoint. No SEC call or extraction is repeated (asserted in tests by counting HTTP requests and `started` events).
* On startup `recover_incomplete()` continues interrupted `running` workflows (`invoke(None)`) and resumes fully-reviewed paused ones.
* Duplicate `POST /audits/start` for a filing with an active workflow returns the existing workflow.

## Decision rules (`decision_service.decide`)
| Level | Triggers |
|---|---|
| **Human Approval Required** | missing mandatory metric · evidence not re-verified · confidence < review floor (90) · blocking validation failure · mandatory anomaly (|YoY| ≥ 50%) · XBRL mismatch · serious unit/period inconsistency |
| **Passed – Human Consideration Recommended** | confidence 90–98 · non-blocking validation warning · warning-level anomaly (≥ 25%) · insufficient history · XBRL missing/unable · optional metric missing |
| **Fully Passed** | none of the above |

Defaults (98 / 90 / 50% / 25% / 0.1%) are **demonstration defaults**. `config.THRESHOLD_BOUNDS` makes it impossible to weaken
the system past the guard rails, and mandatory rules are not configurable at all. Every change is an append-only `ThresholdChange`.

## Confidence (`services/confidence.py`)
`score = Σ weight_i × signal_i / 100`, weights: source quality 15, parsing certainty 20, concept mapping 15, unit consistency 10,
period consistency 10, **XBRL agreement 20**, evidence completeness 10. Confidence measures *extraction evidence*, never approval.

## Data model (`models/entities.py`)
`Company 1─* Filing 1─* AuditWorkflow 1─* MetricResult 1─* {ValidationCheck, AnomalyEvent, ReviewEvent, GroundTruthResult}`;
`WorkflowEvent` (durable progress/audit trail), `ModelUsage`, `ThresholdChange`, `Setting`.
`ReviewEvent` and `ThresholdChange` are append-only: SQLAlchemy `before_update/before_delete` listeners raise `AppendOnlyError`.
`MetricResult.value` is the original extraction and is never overwritten; corrections live in `ReviewEvent.corrected_value` and `MetricResult.final_value`.

## Security notes
* Secrets only in `backend/.env` (git-ignored); the frontend only knows the API URL.
* Reviewer/settings mutations require `X-Reviewer-Token` + `X-Reviewer-Name`. **This is demo authentication** (shared token), not production-grade.
* All requests are validated by Pydantic models; SEC User-Agent carries the configured contact email.
