import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hand, PauseCircle, Settings2, Sparkles, Undo2 } from "lucide-react";
import type { AdaptiveMetric } from "@/types";
import { api, errMsg } from "@/services/api";
import { Badge, Bar, Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, Input, Label } from "@/components/ui/primitives";
import { Callout } from "@/components/audit/Common";
import { dt } from "@/utils/format";
import { cn } from "@/utils/cn";

/** Original vs current threshold on a 60-100 scale. */
export function ThresholdTrack({ original, current }: { original: number; current: number }) {
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - 60) / 40) * 100))}%`;
  const lo = Math.min(original, current), hi = Math.max(original, current);
  const moved = original !== current;
  return (
    <div className="mt-1" aria-label={`Original threshold ${original}%, current threshold ${current}%`}>
      <div className="relative h-2 rounded-full bg-navy-100">
        {moved && <div className="absolute top-0 h-2 rounded-full bg-pass/35" style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />}
        <span className="absolute -top-1 h-4 w-0.5 rounded bg-navy-600/60" style={{ left: pos(original) }} title={`Original ${original}%`} />
        <span className={cn("absolute -top-1.5 h-5 w-1.5 rounded", moved ? "bg-pass" : "bg-navy-700")} style={{ left: pos(current) }} title={`Current ${current}%`} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground"><span>60%</span><span>original {original}% {moved && <>→ now <b className="text-pass">{current}%</b></>}</span><span>100%</span></div>
    </div>
  );
}

export function SourceBadge({ m }: { m: AdaptiveMetric }) {
  if (m.auto_paused) return <Badge tone="warn"><PauseCircle className="h-3 w-3" />Auto-tuning paused</Badge>;
  if (m.source === "auto") return <Badge tone="pass" className="shadow-sm"><Sparkles className="h-3 w-3" />Auto-tuned</Badge>;
  if (m.source === "manual") return <Badge tone="navy"><Hand className="h-3 w-3" />Manual</Badge>;
  return <Badge>Default</Badge>;
}

function ManageDialog({ m, open, onClose }: { m: AdaptiveMetric; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [val, setVal] = useState(String(m.current));
  const [reason, setReason] = useState("");
  const done = () => { qc.invalidateQueries({ queryKey: ["adaptive"] }); onClose(); setReason(""); };
  const set = useMutation({ mutationFn: () => api.adaptiveSet(m.metric_key, Number(val), reason.trim()), onSuccess: done });
  const reset = useMutation({ mutationFn: () => api.adaptiveReset(m.metric_key, reason.trim() || "Reset from dashboard"), onSuccess: done });
  const pause = useMutation({ mutationFn: () => api.adaptivePause(m.metric_key, !m.auto_paused), onSuccess: done });
  const err = set.error ?? reset.error ?? pause.error;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle>Manage threshold · {m.label}</DialogTitle>
        <DialogDescription>Current {m.current}% ({m.source}) · original default {m.default}%. Every change is written to the append-only audit log.</DialogDescription>
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
            <div className="space-y-1.5"><Label htmlFor={`v-${m.metric_key}`}>Set manually (%)</Label><Input id={`v-${m.metric_key}`} type="number" step="1" value={val} onChange={(e) => setVal(e.target.value)} /></div>
            <div className="space-y-1.5"><Label htmlFor={`r-${m.metric_key}`}>Reason (required to set)</Label><Input id={`r-${m.metric_key}`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why are you changing it?" /></div>
          </div>
          <p className="text-xs text-muted-foreground">A manual value is pinned: automatic tuning stays paused for this metric until you resume it.</p>
          {err ? <Callout tone="danger">{errMsg(err)}</Callout> : null}
          <div className="flex flex-wrap justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" disabled={reset.isPending} onClick={() => reset.mutate()}><Undo2 className="h-3.5 w-3.5" />Reset to default ({m.default}%)</Button>
              <Button variant="outline" size="sm" disabled={pause.isPending} onClick={() => pause.mutate()}>{m.auto_paused ? "Resume auto-tuning" : "Pause auto-tuning"}</Button>
            </div>
            <div className="flex gap-2">
              <DialogClose asChild><Button variant="ghost" size="sm">Close</Button></DialogClose>
              <Button size="sm" disabled={set.isPending || reason.trim().length < 3 || Number(val) === m.current} onClick={() => set.mutate()}>Apply</Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AdaptiveCard({ m }: { m: AdaptiveMetric }) {
  const [open, setOpen] = useState(false);
  const tuned = m.source === "auto" && m.last_auto;
  const prev = m.previous ?? m.default;
  const w = m.window;
  const rate = tuned ? m.last_auto!.approval_rate ?? 0 : w.rate ?? 0;
  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0"><div className="eyebrow">Metric</div><h4 className="truncate text-[15px] font-semibold text-navy-900">{m.label}</h4></div>
        <SourceBadge m={m} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-md border bg-white/50 p-3"><div className="text-xs text-muted-foreground">Previous threshold</div><div className="num mt-1 text-2xl font-semibold text-navy-800/70">{prev}%</div></div>
        <div className={cn("rounded-md border p-3", m.source === "auto" ? "border-pass/60 bg-pass-soft" : "bg-white/70")}>
          <div className="text-xs text-muted-foreground">Current threshold</div><div className={cn("num mt-1 text-2xl font-semibold", m.source === "auto" ? "text-pass" : "text-navy-900")}>{m.current}%</div></div>
      </div>
      <ThresholdTrack original={m.default} current={m.current} />

      <div className="mt-4 flex items-center justify-between text-sm"><span className="text-muted-foreground">{tuned ? "Reviewer approval rate" : "Approval rate in learning window"}</span>
        <b className="num">{tuned || w.rate !== null ? `${rate}%` : "—"}</b></div>
      <div className="mt-1"><Bar value={rate} tone="pass" /></div>

      {tuned ? (
        <>
          <p className="mt-3 flex items-center gap-1.5 text-sm font-semibold text-pass"><CheckCircle2 className="h-4 w-4" />Threshold auto-tuned based on reviewer feedback</p>
          <p className="mt-1 text-xs text-muted-foreground">{m.last_auto!.reviews_considered} reviews analysed · {m.last_auto!.approvals} approvals</p>
          <p className="mt-3 border-t pt-3 text-sm italic text-navy-800">“{m.last_auto!.reason}”</p>
        </>
      ) : m.source === "manual" && m.last_change ? (
        <p className="mt-3 border-t pt-3 text-sm italic text-navy-800">“{m.last_change.reason}”</p>
      ) : (
        <>
          <p className="mt-3 text-xs text-muted-foreground">Learning: <b className="num">{w.reviews}</b> of {w.needed_reviews} qualifying reviews collected (confidence {w.low}–{w.high - 1}%){w.reviews > 0 && <> · {w.approvals} approved</>}. Needs ≥ {w.needed_rate}% approvals.</p>
          <div className="mt-1.5"><Bar value={Math.min(100, (w.reviews / w.needed_reviews) * 100)} tone="navy" /></div>
        </>
      )}

      <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
        <span>{m.reviews_total} reviews · {m.adjustments} auto adjustment{m.adjustments === 1 ? "" : "s"}{m.last_adjusted_at && <> · {dt(m.last_adjusted_at)}</>}</span>
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)} aria-label={`Manage ${m.label} threshold`}><Settings2 className="h-3.5 w-3.5" />Manage</Button>
      </div>
      <ManageDialog m={m} open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
