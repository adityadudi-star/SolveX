import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, Calculator, ExternalLink, Eye } from "lucide-react";
import { api, errMsg } from "@/services/api";
import { Badge, Bar, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { DecisionBadge, ReviewStatusBadge, StatusPill } from "@/components/audit/badges";
import { Callout, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt, fullNumber, money, pct } from "@/utils/format";

function Row({ k, children }: { k: string; children: ReactNode }) {
  return <div className="grid gap-1 border-b py-2.5 last:border-0 sm:grid-cols-[11rem_1fr]"><dt className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{k}</dt><dd className="min-w-0 break-words text-sm">{children}</dd></div>;
}

export default function EvidencePage() {
  const { id = "", metricId = "" } = useParams();
  const mid = Number(metricId);
  const metric = useQuery({ queryKey: ["metric", mid], queryFn: () => api.metric(mid) });
  const ex = useQuery({ queryKey: ["explanation", mid], queryFn: () => api.explanation(mid) });

  if (metric.isLoading || ex.isLoading) return <Skeleton className="h-96" />;
  if (metric.error || ex.error) return <ErrorBox message={errMsg(metric.error ?? ex.error)} />;
  const m = metric.data!;
  const e = ex.data!;
  const f = e.observed_facts ?? {};
  const c = e.deterministic_calculations ?? {};
  const conf = c.confidence ?? {};
  const hist = c.historical_comparison ?? {};
  const an = hist.anomaly;
  const xb = c.xbrl_verification;
  const rules: { level: string; rule: string; reason: string }[] = c.decision?.rules_triggered ?? [];

  return (
    <>
      <Link to={`/audits/${id}`} className="mb-3 inline-flex items-center gap-1 text-sm font-medium text-navy-600 hover:underline"><ArrowLeft className="h-4 w-4" />Back to audit</Link>
      <PageHeader title={`${m.label} — evidence & explainability`} subtitle={<>{m.company} · FY{m.fiscal_year}</>}
        actions={<>{<DecisionBadge decision={m.decision} />}<ReviewStatusBadge status={m.review_status} /></>} />

      {m.decision === "HUMAN_APPROVAL_REQUIRED" && (m.confidence ?? 0) >= 98 && (
        <Callout tone="gold" className="mb-5" title="A financial value can be extracted correctly and still be unsafe to approve.">
          Confidence is {m.confidence?.toFixed(0)}/100 — the number is well evidenced — yet a deterministic rule requires human approval: {m.escalation_reasons.join(" ")}
        </Callout>
      )}

      {/* ---------- 1. OBSERVED FACTS ---------- */}
      <Card className="mb-5 border-l-4 border-l-navy-600">
        <CardHeader><CardTitle className="flex items-center gap-2"><Eye className="h-4 w-4 text-navy-600" />Observed facts <Badge tone="navy">from the SEC filing</Badge></CardTitle>
          <CardDescription>What the original document says. Nothing here is computed or generated.</CardDescription></CardHeader>
        <CardContent>
          <dl>
            <Row k="Original SEC source"><a className="inline-flex items-center gap-1 text-navy-600 hover:underline" href={f.source_url} target="_blank" rel="noreferrer">{f.source_url}<ExternalLink className="h-3 w-3 shrink-0" /></a></Row>
            <Row k="Table / section">{f.location ?? f.section}</Row>
            <Row k="Source snippet"><code className="block whitespace-pre-wrap rounded-md border bg-secondary/60 p-2.5 text-xs leading-relaxed">{f.snippet ?? "—"}</code></Row>
            <Row k="Extracted value"><span className="num font-semibold">{money(f.extracted_value, f.currency)}</span> <span className="num text-muted-foreground">({fullNumber(f.extracted_value)}) · shown in filing as “{f.raw_text}”</span>
              {m.final_value !== null && <div className="mt-1 text-navy-600">Reviewer-resolved value: <b className="num">{money(m.final_value, f.currency)}</b> (original preserved)</div>}</Row>
            <Row k="Unit & currency">{f.currency ?? "not stated"} · {f.unit ?? "scale not stated"}</Row>
            <Row k="Reporting period">{f.reporting_period?.start ? `${f.reporting_period.start} → ` : ""}{f.reporting_period?.end} <span className="text-muted-foreground">({f.reporting_period?.type})</span></Row>
            <Row k="XBRL concept (in filing)"><code className="text-xs">{f.xbrl_concept_in_filing}</code></Row>
            <Row k="Extraction method"><Badge tone="navy">{f.extraction_method?.replaceAll("_", " ") ?? "n/a"}</Badge> <span className="ml-1 text-xs text-muted-foreground">evidence re-verified: {f.evidence_verified ? "yes" : "no"}</span>
              {[...(f.evidence_notes ?? []), ...(f.extraction_notes ?? [])].map((n: string, i: number) => <div key={i} className="mt-1 text-xs text-warn">⚠ {n}</div>)}</Row>
          </dl>
        </CardContent>
      </Card>

      {/* ---------- 2. DETERMINISTIC CALCULATIONS ---------- */}
      <Card className="mb-5 border-l-4 border-l-gold-500">
        <CardHeader><CardTitle className="flex items-center gap-2"><Calculator className="h-4 w-4 text-gold-600" />Deterministic calculations <Badge tone="gold">Python · no LLM</Badge></CardTitle>
          <CardDescription>Reproducible arithmetic and rules. The decision below is computed here and cannot be overridden by any model.</CardDescription></CardHeader>
        <CardContent className="space-y-6">
          <section>
            <h4 className="mb-2 text-sm font-semibold">Confidence calculation <span className="num ml-1 rounded bg-navy-50 px-2 py-0.5 text-navy-800">{conf.score?.toFixed?.(2) ?? "—"} / 100</span></h4>
            {conf.signals ? (
              <div className="space-y-2">
                {Object.entries(conf.signals as Record<string, { score: number; why: string }>).map(([k, s]) => (
                  <div key={k} className="grid items-center gap-2 sm:grid-cols-[12rem_1fr_9rem]">
                    <div className="text-sm">{k.replaceAll("_", " ")} <span className="text-xs text-muted-foreground">(weight {conf.weights?.[k]})</span></div>
                    <div><Bar value={s.score} tone={s.score >= 90 ? "pass" : s.score >= 60 ? "warn" : "danger"} /><div className="mt-0.5 text-xs text-muted-foreground">{s.why}</div></div>
                    <div className="num text-right text-sm font-semibold">{s.score} → {(((conf.weights?.[k] ?? 0) * s.score) / 100).toFixed(2)}</div>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">{conf.formula}. Confidence measures extraction evidence quality — it is <b>not</b> audit approval.</p>
              </div>
            ) : <p className="text-sm text-muted-foreground">{conf.note ?? "No signals recorded."}</p>}
          </section>

          <section>
            <h4 className="mb-2 text-sm font-semibold">Accounting & consistency checks</h4>
            <Table><THead><tr><TH>Check</TH><TH>Status</TH><TH>Formula</TH><TH>Explanation</TH></tr></THead>
              <tbody>{(c.validation_checks ?? []).map((v: any, i: number) => (
                <TR key={i}><TD className="font-medium">{v.name}</TD><TD><StatusPill value={v.status} /></TD><TD className="text-xs"><code>{v.formula}</code>{v.tolerance !== null && <div className="text-muted-foreground">tolerance {v.tolerance}%</div>}</TD><TD className="text-xs text-muted-foreground">{v.explanation}</TD></TR>
              ))}</tbody></Table>
          </section>

          <section>
            <h4 className="mb-2 text-sm font-semibold">Historical comparison & anomaly investigation</h4>
            {an ? (
              <div className="grid gap-3 sm:grid-cols-4">
                {[["Current", money(an.current)], ["Previous", money(an.previous)], ["Baseline (3-yr mean)", money(an.baseline)], ["Change", an.pct_change === null ? "n/a" : `${pct(an.pct_change)} (${money(an.abs_change)})`]].map(([l, v]) => (
                  <div key={l} className="rounded-md border p-3"><div className="eyebrow">{l}</div><div className="num mt-1 text-lg font-bold text-navy-900">{v}</div></div>
                ))}
                <div className="rounded-md border p-3 sm:col-span-4">
                  <div className="flex flex-wrap items-center gap-2"><StatusPill value={an.status} /><Badge>severity: {an.severity}</Badge><Badge>threshold {an.threshold}%</Badge>{an.mandatory && <Badge tone="danger">mandatory review</Badge>}</div>
                  <p className="mt-2 text-sm">{an.explanation}</p>
                  <p className="mt-1 text-xs text-muted-foreground">An anomaly is an investigation signal, not proof of fraud. Values are never altered to hide it.</p>
                </div>
              </div>
            ) : <p className="text-sm text-muted-foreground">No anomaly record.</p>}
            {(hist.history ?? []).length > 0 && <p className="mt-2 text-xs text-muted-foreground">Prior annual values (XBRL): {hist.history.map((p: any) => `${p.end}: ${money(p.value)}`).join(" · ")}</p>}
            {(hist.restatements ?? []).length > 0 && <p className="mt-1 text-xs text-warn">Restatement detected: {hist.restatements.map((r: any) => `${r.period_end} originally ${money(r.originally_reported)}, now ${money(r.as_presented_now)}`).join("; ")}</p>}
          </section>

          <section>
            <h4 className="mb-2 text-sm font-semibold">XBRL ground-truth verification</h4>
            {xb ? (
              <div className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2"><StatusPill value={xb.status} /><code className="text-xs">{xb.concept}</code></div>
                <div className="num mt-2 text-sm">XBRL value <b>{money(xb.xbrl_value)}</b> vs extracted <b>{money(f.extracted_value)}</b>{xb.difference !== null && <> · difference {fullNumber(xb.difference)} (tolerance {fullNumber(xb.tolerance)})</>}</div>
                <div className="mt-1 text-xs text-muted-foreground">Period {xb.period_start ? `${xb.period_start} → ` : ""}{xb.period_end} · unit {xb.unit} · accession {xb.accession} · {xb.note}</div>
              </div>
            ) : <p className="text-sm text-muted-foreground">No XBRL comparison (metric not found).</p>}
          </section>

          <section>
            <h4 className="mb-2 text-sm font-semibold">Final decision — rules evaluated (highest severity wins)</h4>
            <div className="mb-2"><DecisionBadge decision={e.decision} /></div>
            <ul className="space-y-1 text-sm">{rules.length === 0 ? <li className="text-muted-foreground">No escalation rule triggered.</li> :
              rules.map((r, i) => <li key={i} className="flex gap-2"><Badge tone={r.level === "HUMAN_APPROVAL_REQUIRED" ? "danger" : "warn"}>{r.rule.replaceAll("_", " ")}</Badge><span className="text-muted-foreground">{r.reason}</span></li>)}</ul>
          </section>
        </CardContent>
      </Card>

      {/* ---------- 3. AI EXPLANATION ---------- */}
      <Card className="mb-5 border-l-4 border-l-slate-400">
        <CardHeader><CardTitle className="flex items-center gap-2"><Bot className="h-4 w-4 text-slate-600" />Explanation <Badge>{e.ai_explanation?.source === "llm" ? `AI-generated · ${e.ai_explanation.model}` : "Deterministic template · no LLM used"}</Badge></CardTitle>
          <CardDescription>{e.ai_explanation?.note}</CardDescription></CardHeader>
        <CardContent><p className="text-sm leading-relaxed">{e.ai_explanation?.text}</p>
          <p className="mt-3 text-xs text-muted-foreground">{e.separation_note}</p></CardContent>
      </Card>

      {m.reviews.length > 0 && (
        <Card><CardHeader><CardTitle>Reviewer history (append-only)</CardTitle></CardHeader><CardContent>
          <ul className="space-y-2 text-sm">{m.reviews.map((r) => (
            <li key={r.id} className="rounded-md border p-3"><b className="capitalize">{r.action}</b> by {r.reviewer} · {dt(r.ts)}<div className="num text-xs text-muted-foreground">original {money(r.original_value)}{r.corrected_value !== null && <> → corrected {money(r.corrected_value)}</>}</div>{r.notes && <div className="mt-1">“{r.notes}”</div>}</li>))}</ul>
        </CardContent></Card>
      )}
    </>
  );
}
