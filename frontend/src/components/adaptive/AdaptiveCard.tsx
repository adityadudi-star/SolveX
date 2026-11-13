import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hand, PauseCircle, Settings2, Sparkles, Undo2 } from "lucide-react";
import type { AdaptiveMetric } from "@/types";
import { api, errMsg } from "@/services/api";
import { Badge, Bar, Button, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, Input, Label } from "@/components/ui/primitives";
import { Callout } from "@/components/audit/Common";
import { dt } from "@/utils/format";
import { cn } from "@/utils/cn";

/** Original vs current threshold on a 60-100 scale (shown only once a threshold has moved). */
export function ThresholdTrack({ original, current }: { original: number; current: number }) {
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - 60) / 40) * 100))}%`;
  const lo = Math.min(original, current), hi = Math.max(original, current);
  return (
    <div className="relative mt-3 h-1.5 rounded-full bg-navy-100" aria-label={`Original threshold ${original}%, current threshold ${current}%`}>
      <div className="absolute top-0 h-1.5 rounded-full bg-pass/40" style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />
      <span className="absolute -top-1 h-3.5 w-0.5 rounded bg-navy-600/50" style={{ left: pos(original) }} title={`Original ${original}%`} />
      <span className="absolute -top-1 h-3.5 w-1.5 rounded bg-pass" style={{ left: pos(current) }} title={`Current ${current}%`} />
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
  const moved = m.current !== m.default;
  return (
    <div className="card-glass card-hover rounded-lg border bg-card p-5">
      <div className="flex items-center justify-between gap-2">
        <h4 className="truncate text-[15px] font-semibold text-foreground">{m.label}</h4>
        <SourceBadge m={m} />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="flex-1 rounded-md border bg-surface/50 px-3 py-2"><div className="text-[11px] text-muted-foreground">Previous</div><div className="num text-xl font-semibold text-muted-foreground">{prev}%</div></div>
        <div className={cn("flex-1 rounded-md border px-3 py-2", m.source === "auto" ? "border-pass/60 bg-pass-soft" : "bg-surface/70")}>
          <div className="text-[11px] text-muted-foreground">Current</div><div className={cn("num text-xl font-semibold", m.source === "auto" ? "text-pass-fg" : "text-foreground")}>{m.current}%</div></div>
      </div>
      {moved && <ThresholdTrack original={m.default} current={m.current} />}

      {tuned ? (
        <div className="mt-4 border-t pt-3">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-pass-fg"><CheckCircle2 className="h-4 w-4" />Auto-tuned from reviewer feedback</p>
          <p className="num mt-1 text-xs text-muted-foreground">{m.last_auto!.reviews_considered} reviews · {m.last_auto!.approval_rate}% approved</p>
        </div>
      ) : m.source === "manual" ? (
        <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">Set manually · auto-tuning paused</p>
      ) : (
        <div className="mt-4 border-t pt-3">
          <div className="flex justify-between text-xs text-muted-foreground"><span>Learning</span><span className="num">{w.reviews} / {w.needed_reviews} reviews</span></div>
          <div className="mt-1.5"><Bar value={Math.min(100, (w.reviews / w.needed_reviews) * 100)} tone="navy" /></div>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span className="num">{m.reviews_total} review{m.reviews_total === 1 ? "" : "s"}</span>
        <Button variant="ghost" size="sm" onClick={() => setOpen(true)} aria-label={`Manage ${m.label} threshold`}><Settings2 className="h-3.5 w-3.5" />Manage</Button>
      </div>
      <ManageDialog m={m} open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
