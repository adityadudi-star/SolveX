import { Link } from "react-router-dom";
import { FileSearch } from "lucide-react";
import type { Metric } from "@/types";
import { Bar, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { DecisionBadge, ReviewStatusBadge, StatusPill } from "@/components/audit/badges";
import { fullNumber, money, pct } from "@/utils/format";

export function MetricsTable({ metrics, workflowId }: { metrics: Metric[]; workflowId: string }) {
  return (
    <Table>
      <THead>
        <tr><TH>Metric</TH><TH>Extracted value</TH><TH>Unit · period</TH><TH>Confidence</TH><TH>Validation</TH><TH>Anomaly</TH><TH>XBRL</TH><TH>Final decision</TH><TH>Evidence</TH></tr>
      </THead>
      <tbody>
        {metrics.map((m) => (
          <TR key={m.id}>
            <TD className="font-semibold text-navy-900">{m.label}</TD>
            <TD className="num">
              {m.found ? (
                <div>
                  <div className="font-semibold" title={fullNumber(m.value)}>{money(m.value, m.currency)}</div>
                  {m.final_value !== null && <div className="text-xs text-navy-600">reviewed: {money(m.final_value, m.currency)}</div>}
                  <div className="text-[11px] text-muted-foreground">as shown: {m.raw_text}</div>
                </div>
              ) : <span className="rounded bg-warn-soft px-1.5 py-0.5 text-xs font-semibold text-warn-fg">MISSING</span>}
            </TD>
            <TD className="whitespace-nowrap text-xs">{m.found ? <>{m.currency ?? "n/a"} · {m.scale === 6 ? "millions" : m.scale === 3 ? "thousands" : m.scale === 9 ? "billions" : m.scale === 0 ? "units" : "scale n/s"}
              <div className="text-muted-foreground">{m.period_end} ({m.period_type})</div></> : "—"}</TD>
            <TD className="w-28">
              {m.found && m.confidence !== null ? <><div className="num text-sm font-semibold">{m.confidence.toFixed(1)}<span className="text-xs font-normal text-muted-foreground">/100</span></div>
                <Bar value={m.confidence} tone={m.confidence >= 98 ? "pass" : m.confidence >= 90 ? "warn" : "danger"} /></> : "—"}
            </TD>
            <TD><StatusPill value={m.validation_status} /></TD>
            <TD><StatusPill value={m.anomaly_status} />{m.anomaly_pct_change !== null && <div className="num mt-1 text-xs text-muted-foreground">{pct(m.anomaly_pct_change)} YoY</div>}</TD>
            <TD><StatusPill value={m.xbrl_status} /></TD>
            <TD><div className="space-y-1"><DecisionBadge decision={m.decision} short /><div><ReviewStatusBadge status={m.review_status} /></div></div></TD>
            <TD><Link to={`/audits/${workflowId}/metrics/${m.id}`} className="inline-flex items-center gap-1 text-xs font-semibold text-navy-600 hover:underline"><FileSearch className="h-3.5 w-3.5" />Evidence</Link></TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
