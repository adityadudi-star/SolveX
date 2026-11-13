import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { ReviewCard } from "@/components/review/ReviewCard";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { Callout, EmptyState, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt, money } from "@/utils/format";
import { cn } from "@/utils/cn";

export default function ReviewCenter() {
  const [tab, setTab] = useState<"queue" | "history">("queue");
  const [flash, setFlash] = useState<string | null>(null);
  const pending = useQuery({ queryKey: ["pending"], queryFn: api.pending, refetchInterval: 6000 });
  const hist = useQuery({ queryKey: ["history"], queryFn: api.history, enabled: tab === "history" });

  return (
    <>
      <PageHeader title="Human Review Center" subtitle="Mandatory reviews pause the workflow at a saved checkpoint. When every mandatory item is resolved, the workflow resumes automatically." />
      {flash && <Callout tone="pass" icon={<CheckCircle2 className="h-4 w-4" />} className="mb-4">{flash}</Callout>}
      <div className="mb-5 inline-flex rounded-md border bg-secondary p-0.5 text-sm font-semibold">
        {([["queue", `Review queue${pending.data ? ` (${pending.data.count})` : ""}`], ["history", "Decision history"]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={cn("rounded px-4 py-1.5", tab === k ? "bg-surface text-navy-800 shadow-sm" : "text-muted-foreground")}>{l}</button>
        ))}
      </div>

      {tab === "queue" && (
        pending.isLoading ? <Skeleton className="h-64" /> : pending.error ? <ErrorBox message={errMsg(pending.error)} /> :
        pending.data!.count === 0 ? (
          <EmptyState title="Nothing awaiting review" body="Metrics that need human approval appear here — low confidence, failed accounting checks, missing evidence, XBRL mismatches or mandatory anomalies." />
        ) : (
          <div className="space-y-5">{pending.data!.pending.map((m) => <ReviewCard key={m.id} m={m} onDone={(msg) => { setFlash(msg); window.scrollTo({ top: 0, behavior: "smooth" }); }} />)}</div>
        )
      )}

      {tab === "history" && (
        <Card><CardHeader><CardTitle>Reviewer decisions</CardTitle><CardDescription>Append-only: original values, corrected values, reviewer identity and timestamps are never overwritten.</CardDescription></CardHeader>
          <CardContent>
            {hist.isLoading ? <Skeleton className="h-40" /> : (hist.data ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No reviewer actions recorded yet.</p> : (
              <Table><THead><tr><TH>When</TH><TH>Reviewer</TH><TH>Audit</TH><TH>Metric</TH><TH>Action</TH><TH>Original</TH><TH>Corrected</TH><TH>Notes</TH></tr></THead>
                <tbody>{hist.data!.map((r) => (
                  <TR key={r.id}><TD className="whitespace-nowrap text-xs">{dt(r.ts)}</TD><TD className="font-medium">{r.reviewer}</TD>
                    <TD><Link className="text-navy-600 hover:underline" to={`/audits/${r.workflow_id}`}>{r.company} FY{r.fiscal_year}</Link></TD><TD>{r.metric}</TD>
                    <TD><Badge tone={r.action === "approve" ? "pass" : r.action === "correct" ? "navy" : "danger"}>{r.action}</Badge></TD>
                    <TD className="num">{money(r.original_value)}</TD><TD className="num">{r.corrected_value !== null ? money(r.corrected_value) : "—"}</TD>
                    <TD className="max-w-xs text-xs text-muted-foreground">{r.notes ?? "—"}</TD></TR>))}</tbody></Table>
            )}
          </CardContent></Card>
      )}
    </>
  );
}
