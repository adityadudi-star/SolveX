import axios, { AxiosError } from "axios";
import type {
  Audit, Explanation, FilingRefDto, Health, Metric, ProgressSnapshot, ReviewEventDto, SettingsDto, Simulation, Summary, Trends, Usage, Company,
} from "@/types";

// Default: same host the page was loaded from, so it works from another device on the LAN / hotspot.
export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? `http://${window.location.hostname}:8000/api`;

export const http = axios.create({ baseURL: API_BASE, timeout: 60_000 });

const SESSION_KEY = "solvex.reviewer";
export interface ReviewerSession { name: string; token: string }
export function getSession(): ReviewerSession | null {
  try { const s = sessionStorage.getItem(SESSION_KEY); return s ? (JSON.parse(s) as ReviewerSession) : null; } catch { return null; }
}
export function setSession(s: ReviewerSession | null) {
  try { s ? sessionStorage.setItem(SESSION_KEY, JSON.stringify(s)) : sessionStorage.removeItem(SESSION_KEY); } catch { /* storage unavailable */ }
}
http.interceptors.request.use((cfg) => {
  const s = getSession();
  if (s) { cfg.headers.set("X-Reviewer-Token", s.token); cfg.headers.set("X-Reviewer-Name", s.name); }
  return cfg;
});

/** Human-readable message from any API/network error (never hides SEC failures). */
export function errMsg(e: unknown): string {
  const ax = e as AxiosError<any>;
  if (ax?.response) {
    const d = ax.response.data?.detail ?? ax.response.data;
    if (typeof d === "string") return d;
    if (d?.error) return d.error;
    if (Array.isArray(d)) return d.map((x: any) => `${(x.loc ?? []).slice(1).join(".")}: ${x.msg}`).join("; ");
    return `Request failed (${ax.response.status})`;
  }
  if (ax?.code === "ERR_NETWORK") return "Cannot reach the SolveX backend. Is it running on http://localhost:8000?";
  return (e as Error)?.message ?? "Unknown error";
}

export const api = {
  health: (live = false) => http.get<Health>("/health", { params: { live } }).then((r) => r.data),
  login: (reviewer: string, token: string) => http.post("/auth/login", { reviewer, token }).then((r) => r.data),
  summary: () => http.get<Summary>("/analytics/summary").then((r) => r.data),
  searchCompanies: (q: string) => http.get<{ results: Company[] }>("/companies/search", { params: { q } }).then((r) => r.data.results),
  filings: (cik: string) => http.get<{ name: string; filings: FilingRefDto[] }>(`/companies/${cik}/filings`, { params: { include_older: true } }).then((r) => r.data),
  startAudit: (cik: string, accession: string, force_new = false) =>
    http.post<{ workflow_id: string; created: boolean; message: string }>("/audits/start", { cik, accession, force_new }).then((r) => r.data),
  audits: (params?: Record<string, string>) => http.get<{ audits: Audit[] }>("/audits", { params }).then((r) => r.data.audits),
  audit: (id: string) => http.get<Audit>(`/audits/${id}`).then((r) => r.data),
  progress: (id: string) => http.get<ProgressSnapshot>(`/audits/${id}/progress`, { params: { format: "json" } }).then((r) => r.data),
  metrics: (id: string) => http.get<{ audit: Audit; metrics: Metric[] }>(`/audits/${id}/metrics`).then((r) => r.data),
  metric: (id: number) => http.get<Metric & { reviews: ReviewEventDto[] }>(`/metrics/${id}`).then((r) => r.data),
  evidence: (id: number) => http.get<Record<string, any>>(`/metrics/${id}/evidence`).then((r) => r.data),
  explanation: (id: number) => http.get<Explanation>(`/metrics/${id}/explanation`).then((r) => r.data),
  pending: () => http.get<{ count: number; pending: Metric[] }>("/reviews/pending").then((r) => r.data),
  history: () => http.get<{ history: ReviewEventDto[] }>("/reviews/history").then((r) => r.data.history),
  approve: (id: number, notes?: string) => http.post(`/reviews/${id}/approve`, { notes }).then((r) => r.data),
  correct: (id: number, corrected_value: number, notes: string) => http.post(`/reviews/${id}/correct`, { corrected_value, notes }).then((r) => r.data),
  reject: (id: number, notes: string) => http.post(`/reviews/${id}/reject`, { notes }).then((r) => r.data),
  trends: (cik: string) => http.get<Trends>("/analytics/trends", { params: { cik } }).then((r) => r.data),
  auditedCompanies: () => http.get<{ companies: Company[] }>("/analytics/companies").then((r) => r.data.companies),
  settings: () => http.get<SettingsDto>("/settings").then((r) => r.data),
  patchThresholds: (body: Record<string, number | string>) => http.patch("/settings/thresholds", body).then((r) => r.data),
  usage: () => http.get<Usage>("/observability/usage").then((r) => r.data),
  simulate: (body: { previous_value: number; current_value: number; extraction_confidence: number; accounting_checks_passed: boolean }) =>
    http.post<Simulation>("/decision/simulate", body).then((r) => r.data),
  reportUrl: (id: string, format: "pdf" | "json") => `${API_BASE}/audits/${id}/report?format=${format}`,
};
