import { AlertTriangle, CheckCircle2, CircleHelp, Hand, ShieldAlert, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import { DECISION, type DecisionKey } from "@/utils/format";

export function DecisionBadge({ decision, short }: { decision: string | null | undefined; short?: boolean }) {
  if (!decision) return <Badge>Pending</Badge>;
  const d = DECISION[decision as DecisionKey];
  if (!d) return <Badge>{decision}</Badge>;
  const Icon = d.tone === "pass" ? CheckCircle2 : d.tone === "warn" ? AlertTriangle : ShieldAlert;
  return <Badge tone={d.tone}><Icon className="h-3 w-3" />{short ? d.short : d.label}</Badge>;
}

const TONES: Record<string, "pass" | "warn" | "danger" | "neutral"> = {
  passed: "pass", normal: "pass", matched: "pass",
  warning: "warn", insufficient_history: "warn", missing: "warn", unable: "warn",
  failed: "danger", mandatory: "danger", mismatched: "danger",
  pending: "neutral",
};
const LABEL: Record<string, string> = {
  insufficient_history: "Insufficient history", unable: "Unable to match", mandatory: "Mandatory review", mismatched: "Mismatched",
};
export function StatusPill({ value }: { value: string | null | undefined }) {
  const v = value ?? "pending";
  const tone = TONES[v] ?? "neutral";
  const Icon = tone === "pass" ? CheckCircle2 : tone === "danger" ? XCircle : tone === "warn" ? AlertTriangle : CircleHelp;
  return <Badge tone={tone}><Icon className="h-3 w-3" />{LABEL[v] ?? v.charAt(0).toUpperCase() + v.slice(1)}</Badge>;
}

export function ReviewStatusBadge({ status }: { status: string }) {
  const map: Record<string, ["pass" | "warn" | "danger" | "navy" | "neutral", string]> = {
    not_required: ["neutral", "No review needed"], optional: ["warn", "Review optional"], pending: ["danger", "Awaiting reviewer"],
    approved: ["pass", "Approved"], corrected: ["navy", "Corrected"], rejected: ["danger", "Rejected"],
  };
  const [tone, label] = map[status] ?? ["neutral", status];
  return <Badge tone={tone}>{status === "pending" && <Hand className="h-3 w-3" />}{label}</Badge>;
}
