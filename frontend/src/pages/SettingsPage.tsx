import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Cpu, Lock, Network, Play, SlidersHorizontal } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errMsg } from "@/services/api";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { DecisionBadge, StatusPill } from "@/components/audit/badges";
import { Callout, ErrorBox, PageHeader } from "@/components/audit/Common";
import { dt, duration, money, pct } from "@/utils/format";

const LABELS: Record<string, [string, string, string]> = {
  approval_confidence: ["Approval confidence threshold", "≥ this (and all checks clean) → potentially Fully Passed", "score"],
  review_confidence: ["Review confidence floor", "Below this → Human Approval Required", "score"],
  anomaly_mandatory_pct: ["Mandatory anomaly threshold", "|YoY change| ≥ this → mandatory human review", "%"],
  anomaly_warning_pct: ["Anomaly warning level", "|YoY change| ≥ this → Human Consideration Recommended", "%"],
  accounting_tolerance_pct: ["Accounting-equation tolerance", "Allowed |A − (L+E)| as % of total assets (pass band)", "%"],
};

function Thresholds() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  useEffect(() => { if (s.data) setDraft(Object.fromEntries(Object.entries(s.data.thresholds).map(([k, v]) => [k, String(v)]))); }, [s.data]);
  const save = useMutation({
    mutationFn: () => api.patchThresholds({ ...Object.fromEntries(Object.entries(draft).filter(([k, v]) => Number(v) !== s.data!.thresholds[k]).map(([k, v]) => [k, Number(v)])), reason }),
    onSuccess: () => { setReason(""); qc.invalidateQueries({ queryKey: ["settings"] }); },
  });
  if (s.isLoading || !s.data) return <Skeleton className="h-64" />;
  const d = s.data;
  const dirty = Object.keys(draft).some((k) => Number(draft[k]) !== d.thresholds[k]);

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4" />Thresholds</CardTitle>
          <CardDescription>Configurable demonstration defaults — not universal accounting standards. New audits snapshot the values in force when they start.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(LABELS).map(([k, [label, hint, unit]]) => (
            <div key={k} className="grid items-center gap-2 sm:grid-cols-[1fr_9rem]">
              <div><Label htmlFor={k}>{label}</Label><div className="text-xs text-muted-foreground">{hint} · allowed {d.bounds[k][0]}–{d.bounds[k][1]} · default {d.defaults[k]}</div></div>
              <div className="flex items-center gap-1.5"><Input id={k} type="number" step="0.1" value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} /><span className="text-xs text-muted-foreground">{unit === "%" ? "%" : ""}</span></div>
            </div>
          ))}
          <div className="space-y-1.5"><Label htmlFor="why">Reason for change</Label><Input id="why" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Recorded in the append-only threshold history" /></div>
          {save.isError && <Callout tone="danger">{errMsg(save.error)}</Callout>}
          {save.isSuccess && !dirty && <Callout tone="pass">Saved and recorded in the change history.</Callout>}
          <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save thresholds"}</Button>
          <Callout tone="navy" icon={<Lock className="h-4 w-4" />} title="Guard rails">{d.notes.join(" ")}</Callout>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Change history</CardTitle><CardDescription>Append-only.</CardDescription></CardHeader>
        <CardContent>{d.changes.length === 0 ? <p className="text-sm text-muted-foreground">No threshold changes yet.</p> :
          <ul className="space-y-2.5 text-sm">{d.changes.map((c) => <li key={c.id} className="rounded-md border p-2.5"><div className="font-medium">{LABELS[c.key]?.[0] ?? c.key}</div><div className="num">{c.old} → <b>{c.new}</b></div><div className="text-xs text-muted-foreground">{c.by} · {dt(c.ts)}{c.reason ? ` · ${c.reason}` : ""}</div></li>)}</ul>}</CardContent>
      </Card>
    </div>
  );
}

function Simulator() {
  const [prev, setPrev] = useState("200000000");
  const [cur, setCur] = useState("500000000");
  const [conf, setConf] = useState("100");
  const [ok, setOk] = useState(true);
  const sim = useMutation({ mutationFn: () => api.simulate({ previous_value: Number(prev), current_value: Number(cur), extraction_confidence: Number(conf), accounting_checks_passed: ok }) });
  useEffect(() => { sim.mutate(); /* eslint-disable-next-line */ }, []);
  const r = sim.data;
  return (
    <Card id="simulator">
      <CardHeader><CardTitle className="flex items-center gap-2"><Play className="h-4 w-4" />Decision simulator — the 100/100-confidence override</CardTitle>
        <CardDescription>Runs the real decision engine on hypothetical inputs (a simulation — nothing is stored, no filing is involved, no LLM is called). Default: revenue $200M → $500M with perfect confidence.</CardDescription></CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-4">
          <div><Label htmlFor="sp">Previous revenue (USD)</Label><Input id="sp" type="number" value={prev} onChange={(e) => setPrev(e.target.value)} /></div>
          <div><Label htmlFor="sc">Current revenue (USD)</Label><Input id="sc" type="number" value={cur} onChange={(e) => setCur(e.target.value)} /></div>
          <div><Label htmlFor="sf">Extraction confidence</Label><Input id="sf" type="number" min={0} max={100} value={conf} onChange={(e) => setConf(e.target.value)} /></div>
          <div className="flex items-end gap-2 pb-2"><input id="so" type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="h-4 w-4" /><Label htmlFor="so">Accounting checks passed</Label></div>
        </div>
        <Button className="mt-3" onClick={() => sim.mutate()} disabled={sim.isPending}>Evaluate</Button>
        {sim.isError && <div className="mt-3"><ErrorBox message={errMsg(sim.error)} /></div>}
        {r && (
          <div className="mt-4 rounded-lg border p-4">
            <div className="flex flex-wrap items-center gap-3"><DecisionBadge decision={r.decision} /><Badge>Change {pct(r.anomaly.pct_change)}</Badge><Badge>Threshold {r.anomaly.threshold}%</Badge><Badge tone="navy">LLM involved: {String(r.llm_involved)}</Badge></div>
            <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm">{r.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
            {r.lesson && <Callout tone="gold" className="mt-3" title={r.lesson}>Confidence {conf}/100 and passing accounting checks do not make a +{r.anomaly.pct_change?.toFixed(0)}% revenue jump safe to approve automatically.</Callout>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Observability() {
  const u = useQuery({ queryKey: ["usage"], queryFn: api.usage, refetchInterval: 10000 });
  const health = useQuery({ queryKey: ["health-live"], queryFn: () => api.health(true), enabled: false });
  if (u.isLoading || !u.data) return <Skeleton className="h-64" />;
  const d = u.data;
  const sec = health.data?.sec ?? d.sec;
  const chart = d.workflows.slice(0, 12).reverse().map((w) => ({ name: `${w.company.split(" ")[0]} ${w.fiscal_year}`, compute: w.compute_ms ?? 0, wall: w.wall_clock_ms ?? 0 }));
  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Network className="h-4 w-4" />SEC API health</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
          <div className="flex items-center gap-2"><StatusPill value={sec.status === "ok" ? "passed" : sec.status === "error" ? "failed" : "warning"} /><span className="capitalize">{sec.status.replace("_", " ")}</span></div>
          <div className="text-xs text-muted-foreground">Requests: {d.sec.requests} · retries: {d.sec.retries} · cache hits: {d.sec.cache_hits}</div>
          {"latency_ms" in sec && sec.latency_ms !== undefined && <div className="text-xs">Live latency: {sec.latency_ms} ms</div>}
          {"last_error" in sec && sec.last_error && <div className="text-xs text-danger">Last error: {sec.last_error}</div>}
          {!d.sec.configured && <Callout tone="warn">SEC_CONTACT_EMAIL is not set in backend/.env.</Callout>}
          <Button variant="outline" size="sm" onClick={() => health.refetch()} disabled={health.isFetching || !d.sec.configured}><Activity className="h-3.5 w-3.5" />{health.isFetching ? "Checking…" : "Run live check"}</Button>
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Cpu className="h-4 w-4" />LLM provider & usage</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
          <div>Provider: <b>{d.llm.provider}</b>{d.llm.model && <> · model <b>{d.llm.model}</b></>} · <Badge tone={d.llm.enabled ? "pass" : "neutral"}>{d.llm.enabled ? "enabled" : "disabled"}</Badge></div>
          <div className="grid grid-cols-2 gap-2 text-xs"><div>Calls <b className="num block text-base">{d.llm.calls}</b></div><div>Retries <b className="num block text-base">{d.llm.retries}</b></div>
            <div>Input tokens <b className="num block text-base">{d.llm.input_tokens.toLocaleString()}</b></div><div>Output tokens <b className="num block text-base">{d.llm.output_tokens.toLocaleString()}</b></div>
            <div>Avg latency <b className="num block text-base">{d.llm.avg_latency_ms} ms</b></div><div>Est. cost <b className="num block text-base">${d.llm.estimated_cost_usd.toFixed(4)}</b></div></div>
          {d.llm.note && <p className="text-xs text-muted-foreground">{d.llm.note}</p>}
        </CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle>Workflow execution time</CardTitle><CardDescription>Compute time excludes time spent waiting for a human reviewer.</CardDescription></CardHeader><CardContent>
        {chart.length === 0 ? <p className="text-sm text-muted-foreground">No completed workflows yet.</p> : (
          <div className="h-60"><ResponsiveContainer><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} width={56} tickFormatter={(v) => duration(v)} />
            <Tooltip formatter={(v: number) => duration(v)} /><Bar dataKey="compute" name="Compute" fill="#12295C" radius={[3, 3, 0, 0]} /><Bar dataKey="wall" name="Wall-clock" fill="#C9971C" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>)}
        {d.workflows.length > 0 && <Table className="mt-3"><THead><tr><TH>Audit</TH><TH>Status</TH><TH>Compute</TH><TH>Wall-clock</TH><TH>SEC requests</TH><TH>Retries</TH><TH>Cache hits</TH></tr></THead>
          <tbody>{d.workflows.map((w) => <TR key={w.workflow_id}><TD>{w.company} FY{w.fiscal_year}</TD><TD className="capitalize">{w.status.replace("_", " ")}</TD><TD className="num">{duration(w.compute_ms)}</TD><TD className="num">{duration(w.wall_clock_ms)}</TD><TD className="num">{w.sec_requests}</TD><TD className="num">{w.sec_retries}</TD><TD className="num">{w.cache_hits}</TD></TR>)}</tbody></Table>}
      </CardContent></Card>
      {d.recent_model_calls.length > 0 && <Card><CardHeader><CardTitle>Recent model calls</CardTitle></CardHeader><CardContent><Table><THead><tr><TH>When</TH><TH>Model</TH><TH>Purpose</TH><TH>In / out tokens</TH><TH>Latency</TH><TH>Retries</TH><TH>Cost</TH></tr></THead>
        <tbody>{d.recent_model_calls.map((c, i) => <TR key={i}><TD className="text-xs">{dt(c.ts)}</TD><TD>{c.provider}/{c.model}</TD><TD>{c.purpose}</TD><TD className="num">{c.input_tokens} / {c.output_tokens}</TD><TD className="num">{c.latency_ms} ms</TD><TD>{c.retries}</TD><TD className="num">{money(c.cost_usd).replace("$", "$")}</TD></TR>)}</tbody></Table></CardContent></Card>}
    </div>
  );
}

export default function SettingsPage() {
  const { hash } = useLocation();
  useEffect(() => { if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" }); }, [hash]);
  return (
    <>
      <PageHeader title="Settings & observability" subtitle="Thresholds, SEC and LLM health, token usage and workflow timing." />
      <div className="space-y-8">
        <Thresholds />
        <Simulator />
        <Observability />
      </div>
    </>
  );
}
