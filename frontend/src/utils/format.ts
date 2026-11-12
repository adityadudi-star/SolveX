const LOCALE = "en-US";

export function money(v: number | null | undefined, currency: string | null = "USD"): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(a / 1e9).toLocaleString(LOCALE, { maximumFractionDigits: 2 })}B`
    : a >= 1e6 ? `${(a / 1e6).toLocaleString(LOCALE, { maximumFractionDigits: 1 })}M`
    : a.toLocaleString(LOCALE, { maximumFractionDigits: 0 });
  const sym = !currency || currency === "USD" ? "$" : `${currency} `;
  return `${v < 0 ? "-" : ""}${sym}${s}`;
}

export function fullNumber(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : v.toLocaleString(LOCALE, { maximumFractionDigits: 2 });
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return "n/a";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function dt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" });
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return s < 90 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

/** Accepts "2,500,000,000", "2500M", "2.5B", "850k". Returns full USD units or null. */
export function parseMoney(input: string): number | null {
  const t = input.trim().replace(/[$,\s]/g, "").toLowerCase();
  const m = /^(-?\d+(?:\.\d+)?)([kmb])?$/.exec(t);
  if (!m) return null;
  const mult = { k: 1e3, m: 1e6, b: 1e9 }[m[2] as "k" | "m" | "b"] ?? 1;
  return parseFloat(m[1]) * mult;
}

export const DECISION = {
  FULLY_PASSED: { label: "Fully Passed", short: "Passed", tone: "pass" },
  PASSED_HUMAN_CONSIDERATION_RECOMMENDED: { label: "Passed – Human Consideration Recommended", short: "Consider review", tone: "warn" },
  HUMAN_APPROVAL_REQUIRED: { label: "Human Approval Required", short: "Approval required", tone: "danger" },
} as const;
export type DecisionKey = keyof typeof DECISION;
