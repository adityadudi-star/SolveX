import { useEffect, useState } from "react";
import { useChartColors } from "@/hooks/useTheme";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Settings2, Sparkles, Undo2 } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errMsg } from "@/services/api";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Select, Skeleton, Table, TD, TH, THead, TR } from "@/components/ui/primitives";
import { Callout, ErrorBox } from "@/components/audit/Common";
import { AdaptiveCard } from "@/components/adaptive/AdaptiveCard";
import { dt } from "@/utils/format";

const PARAMS: [string, string, string][] = [
  ["min_reviews", "Minimum qualifying reviews", "reviews"], ["min_approval_rate", "Minimum approval rate", "%"], ["step", "Adjustment step", "pts"],
  ["min_threshold", "Lowest allowed threshold", "%"], ["max_threshold", "Highest allowed threshold", "%"], ["window_width", "Learning window below threshold", "pts"],
  ["cooldown_minutes", "Cooldown between adjustments", "min"],
];

function ConfigPanel({ cfg, bounds, defaults }: { cfg: Record<string, number>; bounds: Record<string, [number, number]>; defaults: Record<string, number> }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  useEffect(() => setDraft(Object.fromEntries(Object.entries(cfg).map(([k, v]) => [k, String(v)]))), [cfg]);
  const changed = Object.keys(draft).filter((k) => Number(draft[k]) !== cfg[k]);
  const save = useMutation({
    mutationFn: () => api.adaptiveConfig({ ...Object.fromEntries(changed.map((k) => [k, Number(draft[k])])), reason }),
    onSuccess: () => { setReason(""); qc.invalidateQueries({ queryKey: ["adaptive"] }); },
  });
  const resetAll = useMutation({ mutationFn: () => api.adaptiveResetAll("Reset all thresholds from dashboard"), onSuccess: () => qc.invalidateQueries({ queryKey: ["adaptive"] }) });
  const enabled = cfg.auto_tuning_enabled === 1;
  const toggle = useMutation({ mutationFn: () => api.adaptiveConfig({ auto_tuning_enabled: enabled ? 0 : 1, reason: "Toggled from dashboard" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["adaptive"] }) });
  return (
    <Card className="mt-5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Settings2 className="h-4 w-4" />Learning parameters & controls</CardTitle>
        <CardDescription>All parameters are configurable and bounded. Changes are recorded in the settings audit trail.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={enabled ? "pass" : "warn"}>{enabled ? "Auto-tuning ON" : "Auto-tuning OFF"}</Badge>
          <Button variant="outline" size="sm" disabled={toggle.isPending} onClick={() => toggle.mutate()}>{enabled ? "Disable automatic tuning" : "Enable automatic tuning"}</Button>
          <Button variant="outline" size="sm" disabled={resetAll.isPending} onClick={() => { if (window.confirm("Reset EVERY metric to its original default threshold? The history is kept.")) resetAll.mutate(); }}><Undo2 className="h-3.5 w-3.5" />Reset all to defaults</Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PARAMS.map(([k, label, unit]) => (
            <div key={k} className="space-y-1.5"><Label htmlFor={`p-${k}`}>{label} <span className="text-muted-foreground">({unit})</span></Label>
              <Input id={`p-${k}`} type="number" value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
              <div className="text-[11px] text-muted-foreground">{bounds[k][0]}–{bounds[k][1]} · default {defaults[k]}</div></div>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <div className="space-y-1.5"><Label htmlFor="p-reason">Reason for change</Label><Input id="p-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Recorded in the audit trail" /></div>
          <Button disabled={!changed.length || save.isPending} onClick={() => save.mutate()}>Save parameters</Button>
        </div>
        {(save.error ?? resetAll.error ?? toggle.error) ? <Callout tone="danger">{errMsg(save.error ?? resetAll.error ?? toggle.error)}</Callout> : null}
      </CardContent>
    </Card>
  );
}

export default function AdaptiveThresholdSection({ className = "mt-10" }: { className?: string }) {
  const ch = useChartColors();
  const [trendKey, setTrendKey] = useState("all");
  const [histKey, setHistKey] = useState("");
  const ov = useQuery({ queryKey: ["adaptive", "overview"], queryFn: api.adaptiveOverview, refetchInterval: 8000 });
  const hist = useQuery({ queryKey: ["adaptive", "history", histKey], queryFn: () => api.adaptiveHistory(histKey || undefined), refetchInterval: 8000 });

  return (
    <section className={className} aria-labelledby="adaptive-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="adaptive-title" className="flex items-center gap-2 text-xl font-bold text-navy-900"><Brain className="h-5 w-5" />Adaptive Threshold Engine</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">SolveX learns from your reviewers, metric by metric. When reviewers keep approving items just below a metric’s confidence threshold, that
            metric’s threshold is lowered one controlled step — with a full audit trail. It only affects <b>new</b> decisions.</p>
        </div>
        {ov.data && <div className="flex flex-wrap gap-2 text-xs">
          <Badge tone={ov.data.config.auto_tuning_enabled ? "pass" : "warn"}>{ov.data.config.auto_tuning_enabled ? "Auto-tuning on" : "Auto-tuning off"}</Badge>
          <Badge>{ov.data.totals.reviews} feedback records</Badge><Badge tone="navy"><Sparkles className="h-3 w-3" />{ov.data.totals.auto_adjustments} auto adjustment{ov.data.totals.auto_adjustments === 1 ? "" : "s"}</Badge>
        </div>}
      </div>

      {ov.isLoading ? <Skeleton className="h-72" /> : ov.error ? <ErrorBox message={errMsg(ov.error)} /> : ov.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{ov.data.metrics.map((m) => <AdaptiveCard key={m.metric_key} m={m} />)}</div>

          <Card className="mt-5">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div><CardTitle>Reviewer approval trend</CardTitle><CardDescription>Cumulative approval rate across reviewer decisions, in order.</CardDescription></div>
                <Select className="w-52" value={trendKey} onChange={(e) => setTrendKey(e.target.value)} aria-label="Trend metric">
                  <option value="all">All metrics</option>{ov.data.metrics.map((m) => <option key={m.metric_key} value={m.metric_key}>{m.label}</option>)}</Select>
              </div>
            </CardHeader>
            <CardContent>
              {(ov.data.trend[trendKey] ?? []).length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No reviewer feedback recorded yet. Approvals and rejections in the Human Review Center appear here.</p> : (
                <div className="h-56"><ResponsiveContainer><LineChart data={ov.data.trend[trendKey]}>
                  <CartesianGrid strokeDasharray="3 3" stroke={ch.grid} vertical={false} /><XAxis dataKey="n" tick={{ fontSize: 11 }} label={{ value: "review #", position: "insideBottom", offset: -2, fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} width={44} /><Tooltip formatter={(v: number) => [`${v}%`, "Approval rate"]} labelFormatter={(n) => `After review #${n}`} />
                  <Line type="monotone" dataKey="rate" stroke={ch.series[2]} strokeWidth={2.5} dot={{ r: 3 }} /></LineChart></ResponsiveContainer></div>
              )}
            </CardContent>
          </Card>

          <ConfigPanel cfg={ov.data.config} bounds={ov.data.bounds} defaults={ov.data.defaults} />

          <Card className="mt-5">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div><CardTitle>Adjustment history</CardTitle><CardDescription>Append-only: why each threshold changed, on how many reviews, and who or what changed it.</CardDescription></div>
                <Select className="w-52" value={histKey} onChange={(e) => setHistKey(e.target.value)} aria-label="History metric">
                  <option value="">All metrics</option>{ov.data.metrics.map((m) => <option key={m.metric_key} value={m.metric_key}>{m.label}</option>)}</Select>
              </div>
            </CardHeader>
            <CardContent>
              {hist.isLoading ? <Skeleton className="h-24" /> : (hist.data ?? []).length === 0 ? <p className="text-sm text-muted-foreground">No threshold changes yet — every metric is still at its original default.</p> : (
                <Table><THead><tr><TH>When</TH><TH>Metric</TH><TH>Type</TH><TH>Change</TH><TH>Reviews</TH><TH>Approval</TH><TH>Reason</TH><TH>By</TH></tr></THead>
                  <tbody>{hist.data!.map((h) => (
                    <TR key={h.id}><TD className="whitespace-nowrap text-xs">{dt(h.ts)}</TD><TD className="font-medium">{h.metric}</TD>
                      <TD><Badge tone={h.kind === "auto" ? "pass" : h.kind === "manual" ? "navy" : "warn"}>{h.kind}</Badge></TD>
                      <TD className="num whitespace-nowrap">{h.previous}% → <b>{h.new}%</b></TD>
                      <TD className="num">{h.reviews_considered ?? "—"}</TD><TD className="num">{h.approval_rate !== null ? `${h.approval_rate}%` : "—"}</TD>
                      <TD className="min-w-[16rem] text-xs text-muted-foreground">{h.reason}{h.window_low !== null && <div className="mt-0.5">Window evaluated: {h.window_low}–{(h.window_high ?? 0) - 1}%</div>}</TD>
                      <TD className="text-xs">{h.changed_by}</TD></TR>))}</tbody></Table>
              )}
            </CardContent>
          </Card>
          <p className="mt-3 text-xs text-muted-foreground">{ov.data.note} Reviewer approvals are only counted when an item was flagged <i>solely</i> for low confidence, and each decision is judged against the threshold that was active when it was made.</p>
        </>
      )}
    </section>
  );
}
