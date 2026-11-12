import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { TrendChart } from "@/components/charts/TrendChart";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Select, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { EmptyState, ErrorBox, PageHeader } from "@/components/audit/Common";
import { money, pct } from "@/utils/format";

export default function Trends() {
  const cos = useQuery({ queryKey: ["audited-companies"], queryFn: api.auditedCompanies });
  const [cik, setCik] = useState("");
  useEffect(() => { if (!cik && cos.data?.length) setCik(cos.data[0].cik); }, [cos.data, cik]);
  const t = useQuery({ queryKey: ["trends", cik], queryFn: () => api.trends(cik), enabled: !!cik });

  if (cos.isLoading) return <Skeleton className="h-64" />;
  if (!cos.data?.length) return (<><PageHeader title="Historical financial analysis" /><EmptyState title="No audited companies yet" body="Run an audit and SolveX will store multi-year XBRL history for trend analysis." action={<Button asChild><Link to="/audits/new">New audit</Link></Button>} /></>);

  const tr = t.data;
  const rows = tr ? Object.entries(tr.series).flatMap(([k, s]) => s.points.map((p) => ({ k, label: s.label, ...p }))).filter((r) => r.pct_change !== null).sort((a, b) => b.year - a.year || a.label.localeCompare(b.label)) : [];

  return (
    <>
      <PageHeader title="Historical financial analysis" subtitle="Built entirely from results stored by SolveX audits (current values + XBRL annual history)."
        actions={<Select className="w-64" value={cik} onChange={(e) => setCik(e.target.value)} aria-label="Company">{cos.data.map((c) => <option key={c.cik} value={c.cik}>{c.name}{c.ticker ? ` (${c.ticker})` : ""}</option>)}</Select>} />
      {t.isLoading ? <Skeleton className="h-96" /> : t.error ? <ErrorBox message={errMsg(t.error)} /> : tr && (
        <>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card><CardHeader><CardTitle>Revenue & net income</CardTitle></CardHeader><CardContent><TrendChart trends={tr} keys={["revenue", "net_income"]} /></CardContent></Card>
            <Card><CardHeader><CardTitle>Assets, liabilities & equity</CardTitle></CardHeader><CardContent><TrendChart trends={tr} kind="bar" keys={["total_assets", "total_liabilities", "shareholders_equity"]} /></CardContent></Card>
            <Card><CardHeader><CardTitle>Cash flow</CardTitle><CardDescription>Operating cash flow and capital expenditure.</CardDescription></CardHeader><CardContent><TrendChart trends={tr} keys={["operating_cash_flow", "capital_expenditure", "cash_and_equivalents"]} /></CardContent></Card>
            <Card><CardHeader><CardTitle>Operating expenses</CardTitle></CardHeader><CardContent><TrendChart trends={tr} kind="bar" keys={["operating_expenses"]} /></CardContent></Card>
          </div>
          <Card className="mt-5">
            <CardHeader><CardTitle>Year-over-year changes & unusual movements</CardTitle>
              <CardDescription>Warning ≥ {tr.thresholds.anomaly_warning_pct}% · mandatory-review level ≥ {tr.thresholds.anomaly_mandatory_pct}%. Indicators are investigation signals, not proof of error.</CardDescription></CardHeader>
            <CardContent>
              <Table><THead><tr><TH>Year</TH><TH>Metric</TH><TH>Value</TH><TH>Abs. change</TH><TH>% change</TH><TH>Indicator</TH></tr></THead>
                <tbody>{rows.map((r) => (
                  <TR key={`${r.k}${r.year}`}><TD>{r.year}</TD><TD className="font-medium">{r.label}</TD><TD className="num">{money(r.value)}</TD><TD className="num">{money(r.abs_change)}</TD>
                    <TD className="num font-semibold">{pct(r.pct_change)}</TD>
                    <TD>{r.mandatory_level ? <Badge tone="danger"><AlertTriangle className="h-3 w-3" />Mandatory-level movement</Badge> : r.unusual ? <Badge tone="warn"><AlertTriangle className="h-3 w-3" />Unusual</Badge> : <Badge tone="pass">Normal</Badge>}</TD></TR>))}</tbody></Table>
              {rows.length === 0 && <p className="text-sm text-muted-foreground">Not enough history to compute changes.</p>}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}
