import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileDown, Hand, ShieldAlert } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { useAuditProgress } from "@/hooks/useAuditProgress";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { MetricsTable } from "@/components/audit/MetricsTable";
import { DecisionBadge } from "@/components/audit/badges";
import { ProgressTimeline } from "@/components/audit/ProgressTimeline";
import { Callout, EmptyState, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt, duration } from "@/utils/format";

export default function AuditResults() {
  const { id = "" } = useParams();
  const q = useQuery({
    queryKey: ["metrics", id], queryFn: () => api.metrics(id),
    refetchInterval: (query) => (["running"].includes(query.state.data?.audit.status ?? "running") ? 2000 : 6000),
  });
  const running = q.data?.audit.status === "running";
  const { snap, transport } = useAuditProgress(running ? id : null);

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.error) return <ErrorBox message={errMsg(q.error)} />;
  const { audit: a, metrics } = q.data!;
  const x = a.summary.xbrl;
  const overrides = metrics.filter((m) => m.found && (m.confidence ?? 0) >= 98 && m.decision === "HUMAN_APPROVAL_REQUIRED");

  return (
    <>
      <PageHeader
        title={`${a.company.name} · FY${a.filing.fiscal_year} ${a.filing.form}`}
        subtitle={<>Period ended {a.filing.period_end} · accession {a.filing.accession} · <a className="inline-flex items-center gap-0.5 text-navy-600 hover:underline" href={a.filing.url} target="_blank" rel="noreferrer">original SEC filing <ExternalLink className="h-3 w-3" /></a></>}
        actions={<>
          {a.status === "completed" && <>
            <Button asChild variant="outline"><a href={api.reportUrl(a.workflow_id, "pdf")}><FileDown className="h-4 w-4" />PDF report</a></Button>
            <Button asChild variant="outline"><a href={api.reportUrl(a.workflow_id, "json")} target="_blank" rel="noreferrer">JSON</a></Button></>}
        </>} />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        {a.status === "failed" ? <span className="rounded-full border border-red-200 bg-danger-soft px-3 py-1 text-sm font-semibold text-danger">Audit failed</span> : <DecisionBadge decision={a.decision} />}
        <span className="text-xs text-muted-foreground">Started {dt(a.started_at)} · wall-clock {duration(a.duration_ms)} · status <b>{a.status.replace("_", " ")}</b></span>
      </div>

      {a.status === "completed" && a.decision === "HUMAN_APPROVAL_REQUIRED" && (
        <Callout tone="pass" className="mb-5" title="Automated decision resolved by human review">
          The automated decision stays <b>Human Approval Required</b> (it is never rewritten); reviewers resolved every mandatory item —{" "}
          {a.summary.reviewed?.approve ?? 0} approved · {a.summary.reviewed?.correct ?? 0} corrected · {a.summary.reviewed?.reject ?? 0} rejected. Original values and the full reviewer trail are preserved.
        </Callout>
      )}

      {a.status === "failed" && (
        <div className="mb-5 space-y-2"><ErrorBox message={a.error ?? "Unknown failure"} /><p className="text-sm text-muted-foreground">SolveX never fabricates SEC data: nothing was extracted for this run. Fix the cause (e.g. SEC_CONTACT_EMAIL, connectivity) and start a new audit.</p></div>
      )}

      {a.status === "awaiting_review" && (
        <Callout tone="danger" icon={<Hand className="h-4 w-4" />} title="Workflow paused — mandatory human review" className="mb-5">
          {a.summary.pending_reviews ?? "Some"} metric(s) need a reviewer. The workflow is checkpointed and will resume automatically once every mandatory item is approved, corrected or rejected.{" "}
          <Link to="/reviews" className="font-semibold underline">Open the Human Review Center →</Link>
        </Callout>
      )}

      {overrides.length > 0 && (
        <Callout tone="gold" icon={<ShieldAlert className="h-4 w-4 text-danger" />} className="mb-5" title="A financial value can be extracted correctly and still be unsafe to approve.">
          {overrides.map((m) => `${m.label} (${m.confidence?.toFixed(0)}/100 confidence, ${m.anomaly_pct_change !== null ? `${m.anomaly_pct_change > 0 ? "+" : ""}${m.anomaly_pct_change.toFixed(1)}% YoY` : m.escalation_reasons[0]})`).join("; ")}
          {" "}— extraction confidence is high, but the decision engine requires a human. No model can override this.
        </Callout>
      )}

      {running && (
        <Card className="mb-5"><CardHeader><CardTitle>Audit in progress</CardTitle></CardHeader>
          <CardContent>{snap ? <ProgressTimeline stages={snap.stages} transport={transport} /> : <Skeleton className="h-40" />}</CardContent></Card>
      )}

      {metrics.length === 0 ? (
        !running && a.status !== "failed" && <EmptyState title="No metrics stored for this audit" />
      ) : (
        <Card>
          <CardHeader><CardTitle>Extracted financial metrics</CardTitle>
            <CardDescription>{metrics.filter((m) => m.found).length} of {metrics.length} metrics found. Missing metrics are never treated as zero. Capital expenditure is shown as the positive cash payment.</CardDescription></CardHeader>
          <CardContent><MetricsTable metrics={metrics} workflowId={a.workflow_id} /></CardContent>
        </Card>
      )}

      {x && (
        <Card className="mt-5">
          <CardHeader><CardTitle>XBRL ground-truth verification</CardTitle><CardDescription>Actual match counts for this audit — no accuracy claims beyond them.</CardDescription></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {[["Matched", x.matched, "text-pass"], ["Mismatched", x.mismatched, "text-danger"], ["Missing in XBRL", x.missing, "text-warn"], ["Unable to match", x.unable, "text-warn"], ["Metrics found", x.metrics_found, "text-navy-800"]].map(([l, v, c]) => (
                <div key={l as string} className="rounded-md border p-3"><div className="eyebrow">{l}</div><div className={`num mt-1 text-2xl font-bold ${c}`}>{v}</div></div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground"><b>Methodology.</b> {x.methodology}</p>
          </CardContent>
        </Card>
      )}
    </>
  );
}
