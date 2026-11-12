import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Building2, CheckCircle2, ClipboardCheck, FileText, Hand, Ruler, ShieldAlert, Sigma } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { StatCard } from "@/components/dashboard/StatCard";
import { DecisionChart } from "@/components/dashboard/DecisionChart";
import { DecisionBadge } from "@/components/audit/badges";
import { Callout, EmptyState, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt } from "@/utils/format";
import { cn } from "@/utils/cn";

export default function Overview() {
  const { data, isLoading, error } = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: 8000 });
  const [view, setView] = useState<"audits" | "metrics">("audits");
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.health(false), refetchInterval: 30000 });

  if (error) return <ErrorBox message={errMsg(error)} />;
  const d = data;
  const byD = d ? (view === "audits" ? d.audits_by_decision : d.metrics_by_decision) : undefined;

  return (
    <>
      <PageHeader title="Overview" subtitle="Live statistics from the SolveX audit database."
        actions={<Button asChild variant="gold"><Link to="/audits/new">Start a new audit</Link></Button>} />

      {health.data && !health.data.sec.configured && (
        <Callout tone="warn" icon={<AlertTriangle className="h-4 w-4" />} title="SEC access not configured" className="mb-5">
          Set <b>SEC_CONTACT_EMAIL</b> in <code>backend/.env</code> to a real contact email (SEC fair-access policy) and restart the backend. No SEC data is fabricated while unconfigured.
        </Callout>
      )}

      <Callout tone="gold" icon={<Sigma className="h-4 w-4 text-gold-600" />} className="mb-6" title="A financial value can be extracted correctly and still be unsafe to approve.">
        SolveX separates <b>extraction confidence</b> from <b>audit approval</b>: a 100/100-confidence number that moved +150% year over year still requires a human.{" "}
        <Link to="/settings#simulator" className="font-semibold underline">Try the decision simulator →</Link>
      </Callout>

      {isLoading || !d ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Companies audited" value={d.companies_audited} icon={<Building2 className="h-5 w-5" />} />
            <StatCard label="Filings processed" value={d.filings_processed} icon={<FileText className="h-5 w-5" />} hint={`${d.audits_total} audit run(s)`} />
            <StatCard label="Metrics extracted" value={d.metrics_extracted} icon={<Ruler className="h-5 w-5" />} tone="gold" />
            <StatCard label="Pending reviews" value={d.pending_reviews} icon={<Hand className="h-5 w-5" />} tone={d.pending_reviews ? "danger" : "navy"} hint={`${d.audits_awaiting_review} audit(s) paused`} />
            <StatCard label="Fully passed" value={d.audits_by_decision.FULLY_PASSED} icon={<CheckCircle2 className="h-5 w-5" />} tone="pass" hint="audits" />
            <StatCard label="Human consideration recommended" value={d.audits_by_decision.PASSED_HUMAN_CONSIDERATION_RECOMMENDED} icon={<AlertTriangle className="h-5 w-5" />} tone="warn" hint="audits" />
            <StatCard label="Human approval required" value={d.audits_by_decision.HUMAN_APPROVAL_REQUIRED} icon={<ShieldAlert className="h-5 w-5" />} tone="danger" hint="audits" />
            <StatCard label="Reviewer actions" value={d.reviewer_actions} icon={<ClipboardCheck className="h-5 w-5" />} hint="append-only history" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_22rem]">
            <Card>
              <CardHeader><CardTitle>Recent audit activity</CardTitle><CardDescription>Latest workflow runs, newest first.</CardDescription></CardHeader>
              <CardContent>
                {d.recent_audits.length === 0 ? (
                  <EmptyState title="No audits yet" body="Search a company, pick a Form 10-K and SolveX will retrieve it from SEC EDGAR, extract the metrics and verify them against XBRL." action={<Button asChild><Link to="/audits/new">Run your first audit</Link></Button>} />
                ) : (
                  <ul className="divide-y">
                    {d.recent_audits.map((a) => (
                      <li key={a.workflow_id}>
                        <Link to={`/audits/${a.workflow_id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-secondary/40 -mx-2 px-2 rounded-md">
                          <div>
                            <div className="text-sm font-semibold text-navy-900">{a.company.name} <span className="font-normal text-muted-foreground">· FY{a.filing.fiscal_year} {a.filing.form}</span></div>
                            <div className="text-xs text-muted-foreground">{dt(a.started_at)} · <span className={cn(a.status === "failed" && "font-semibold text-danger")}>{a.status.replace("_", " ")}</span></div>
                          </div>
                          {a.status === "failed" ? <span className="text-xs font-medium text-danger">Failed — see details</span> : <DecisionBadge decision={a.decision} short />}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Audit decision distribution</CardTitle>
                <div className="mt-2 inline-flex rounded-md border bg-secondary p-0.5 text-xs font-semibold">
                  {(["audits", "metrics"] as const).map((v) => (
                    <button key={v} onClick={() => setView(v)} className={cn("rounded px-3 py-1 capitalize", view === v ? "bg-white shadow-sm text-navy-800" : "text-muted-foreground")}>{v}</button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>{byD && <DecisionChart data={byD} />}</CardContent>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
