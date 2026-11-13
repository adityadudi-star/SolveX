export type DecisionCode = "FULLY_PASSED" | "PASSED_HUMAN_CONSIDERATION_RECOMMENDED" | "HUMAN_APPROVAL_REQUIRED";

export interface Company { cik: string; name: string; ticker: string | null }
export interface FilingRefDto {
  accession: string; form: string; filing_date: string | null; period_end: string | null;
  fiscal_year: number | null; primary_document: string; url: string;
}

export interface Audit {
  workflow_id: string; status: "running" | "awaiting_review" | "completed" | "failed";
  current_stage: string; completed_stages: string[]; decision: DecisionCode | null; decision_label: string | null;
  error: string | null; company: Company;
  filing: { form: string; accession: string; filing_date: string | null; period_end: string | null; fiscal_year: number | null; url: string };
  started_at: string; finished_at: string | null; duration_ms: number | null;
  summary: { by_decision?: Record<DecisionCode, number>; metrics_total?: number; pending_reviews?: number; pending_reviews_initial?: number; reviewed?: Record<string, number>;
    xbrl?: { matched: number; mismatched: number; missing: number; unable: number; metrics_found: number; methodology: string; match_rate_pct: number | null } };
  stats: Record<string, number | boolean>;
  thresholds?: Record<string, number>;
}

export interface Metric {
  id: number; workflow_id: string; metric_key: string; label: string; statement: string; found: boolean;
  value: number | null; final_value: number | null; currency: string | null; unit: string | null; scale: number | null; raw_text: string | null;
  period_start: string | null; period_end: string | null; period_type: string | null; xbrl_concept: string | null;
  confidence: number | null; validation_status: string; anomaly_status: string; xbrl_status: string;
  decision: DecisionCode | null; escalation_reasons: string[]; review_status: string; evidence_verified: boolean;
  extraction_method: string | null; section: string | null; location: string | null; source_url: string | null;
  company?: string; ticker?: string; fiscal_year?: number; anomaly_pct_change: number | null; anomaly_severity: string | null;
  snippet?: string; anomaly_explanation?: string | null;
}

export interface StageView { stage: string; label: string; state: "pending" | "running" | "completed" | "paused" | "failed"; message: string; ts: string | null }
export interface ProgressSnapshot { workflow_id?: string; status: Audit["status"]; current_stage: string; error: string | null; stages: StageView[] }

export interface Summary {
  companies_audited: number; filings_processed: number; audits_total: number; metrics_extracted: number;
  audits_by_decision: Record<DecisionCode, number>; metrics_by_decision: Record<DecisionCode, number>;
  pending_reviews: number; audits_awaiting_review: number; audits_failed: number; reviewer_actions: number; recent_audits: Audit[];
}

export interface ReviewEventDto {
  id: number; metric_id: number; workflow_id: string; metric: string; company: string; fiscal_year: number | null; action: "approve" | "correct" | "reject";
  reviewer: string; original_value: number | null; corrected_value: number | null; notes: string | null;
  previous_review_status: string; new_review_status: string; ts: string;
}

export interface TrendPoint { period_end: string; year: number; value: number; source: string; pct_change: number | null; abs_change: number | null; unusual: boolean; mandatory_level: boolean }
export interface Trends { company: Company; series: Record<string, { label: string; points: TrendPoint[] }>; thresholds: Record<string, number>; note?: string }

export interface SettingsDto {
  thresholds: Record<string, number>; defaults: Record<string, number>; bounds: Record<string, [number, number]>; notes: string[];
  changes: { id: number; key: string; old: number; new: number; by: string; reason: string | null; ts: string }[];
  sec: { configured: boolean; status: string; user_agent: string | null; last_ok: string | null; last_error: string | null; latency_ms?: number };
  llm: { provider: string; model: string | null; enabled: boolean };
  auth: { mode: string; warning: string };
}

export interface Usage {
  llm: { provider: string; model: string | null; enabled: boolean; calls: number; input_tokens: number; output_tokens: number; avg_latency_ms: number; retries: number; estimated_cost_usd: number; note: string };
  sec: { status: string; requests: number; retries: number; cache_hits: number; configured: boolean };
  workflows: { workflow_id: string; company: string; fiscal_year: number | null; status: string; wall_clock_ms: number | null; compute_ms: number | null; sec_requests: number; sec_retries: number; cache_hits: number }[];
  recent_model_calls: { ts: string; provider: string; model: string; purpose: string; input_tokens: number; output_tokens: number; latency_ms: number; retries: number; cost_usd: number; success: boolean }[];
}

export interface Health { status: string; app: string; version: string; database: string; sec: SettingsDto["sec"]; llm: { provider: string; model: string | null; enabled: boolean; mode: string } }

export interface Explanation {
  metric_id: number; label: string; decision: DecisionCode | null;
  observed_facts: Record<string, any>; deterministic_calculations: Record<string, any>;
  ai_explanation: { source: "llm" | "template"; provider: string | null; model: string | null; text: string; note: string; template_text?: string };
  separation_note: string;
}

export interface AdaptiveAdjustmentDto {
  id: number; metric_key: string; metric: string; kind: "auto" | "manual" | "reset"; previous: number; new: number; reason: string;
  reviews_considered: number | null; approvals: number | null; approval_rate: number | null; window_low: number | null; window_high: number | null;
  changed_by: string; ts: string;
}
export interface AdaptiveMetric {
  metric_key: string; label: string; default: number; current: number; previous: number | null; source: "default" | "auto" | "manual";
  auto_paused: boolean; epoch: number; adjustments: number; last_adjusted_at: string | null; last_adjustment_kind: string | null;
  reviews_total: number; approval_pct_total: number | null;
  window: { low: number; high: number; reviews: number; approvals: number; rate: number | null; needed_reviews: number; needed_rate: number };
  last_auto: AdaptiveAdjustmentDto | null; last_change: AdaptiveAdjustmentDto | null;
}
export interface AdaptiveOverview {
  config: Record<string, number>; bounds: Record<string, [number, number]>; defaults: Record<string, number>;
  metrics: AdaptiveMetric[]; trend: Record<string, { n: number; rate: number; ts: string }[]>;
  totals: { reviews: number; auto_adjustments: number; changes: number }; note: string;
}

export interface Simulation {
  simulation: boolean; decision: DecisionCode; decision_label: string; reasons: string[]; rules_triggered: { level: string; rule: string; reason: string }[];
  anomaly: { pct_change: number | null; abs_change: number | null; threshold: number; status: string; mandatory: boolean; explanation: string };
  lesson: string | null; llm_involved: boolean;
}
