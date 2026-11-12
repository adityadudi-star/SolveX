import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errMsg } from "@/services/api";
import { Badge, Button, Card, CardContent, Select, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { DecisionBadge } from "@/components/audit/badges";
import { EmptyState, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt, duration } from "@/utils/format";

export default function AuditHistory() {
  const [status, setStatus] = useState("");
  const [decision, setDecision] = useState("");
  const q = useQuery({ queryKey: ["audits", status, decision], queryFn: () => api.audits({ ...(status && { status }), ...(decision && { decision }) }), refetchInterval: 8000 });

  return (
    <>
      <PageHeader title="Audit history" subtitle="Every audit run with its decision, timing and reviewer actions."
        actions={<>
          <Select className="w-44" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"><option value="">All statuses</option><option value="completed">Completed</option><option value="awaiting_review">Awaiting review</option><option value="running">Running</option><option value="failed">Failed</option></Select>
          <Select className="w-64" value={decision} onChange={(e) => setDecision(e.target.value)} aria-label="Decision"><option value="">All decisions</option><option value="FULLY_PASSED">Fully Passed</option><option value="PASSED_HUMAN_CONSIDERATION_RECOMMENDED">Human Consideration Recommended</option><option value="HUMAN_APPROVAL_REQUIRED">Human Approval Required</option></Select>
        </>} />
      {q.isLoading ? <Skeleton className="h-64" /> : q.error ? <ErrorBox message={errMsg(q.error)} /> : q.data!.length === 0 ? (
        <EmptyState title="No audit runs match" action={<Button asChild><Link to="/audits/new">Start an audit</Link></Button>} />
      ) : (
        <Card><CardContent className="p-0 pt-2">
          <Table><THead><tr><TH>Company</TH><TH>Filing period</TH><TH>Decision</TH><TH>Status</TH><TH>Reviewer actions</TH><TH>Started</TH><TH>Duration</TH><TH></TH></tr></THead>
            <tbody>{q.data!.map((a) => {
              const r = a.summary.reviewed ?? {};
              const n = (r.approve ?? 0) + (r.correct ?? 0) + (r.reject ?? 0);
              return (
                <TR key={a.workflow_id}>
                  <TD><div className="font-semibold text-navy-900">{a.company.name}</div><div className="text-xs text-muted-foreground">{a.company.ticker} · CIK {a.company.cik}</div></TD>
                  <TD className="text-sm">FY{a.filing.fiscal_year} {a.filing.form}<div className="text-xs text-muted-foreground">ended {a.filing.period_end}</div></TD>
                  <TD>{a.status === "failed" ? <Badge tone="danger">Failed</Badge> : <DecisionBadge decision={a.decision} short />}</TD>
                  <TD className="text-sm capitalize">{a.status.replace("_", " ")}</TD>
                  <TD className="text-xs">{n ? `${r.approve ?? 0} approved · ${r.correct ?? 0} corrected · ${r.reject ?? 0} rejected` : a.status === "awaiting_review" ? `${a.summary.pending_reviews_initial ?? "…"} pending` : "—"}</TD>
                  <TD className="whitespace-nowrap text-xs">{dt(a.started_at)}</TD><TD className="text-xs">{duration(a.duration_ms)}</TD>
                  <TD><Link className="text-sm font-semibold text-navy-600 hover:underline" to={`/audits/${a.workflow_id}`}>Open</Link></TD>
                </TR>);
            })}</tbody></Table>
        </CardContent></Card>
      )}
    </>
  );
}
