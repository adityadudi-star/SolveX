import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, FilePenLine, X } from "lucide-react";
import type { Metric } from "@/types";
import { api, errMsg } from "@/services/api";
import { Badge, Bar, Button, Card, Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, Input, Label, Textarea } from "@/components/ui/primitives";
import { StatusPill } from "@/components/audit/badges";
import { Callout } from "@/components/audit/Common";
import { fullNumber, money, parseMoney, pct } from "@/utils/format";

type Mode = "approve" | "correct" | "reject" | null;

export function ReviewCard({ m, onDone }: { m: Metric; onDone: (msg: string) => void }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>(null);
  const [notes, setNotes] = useState("");
  const [val, setVal] = useState("");
  const parsed = parseMoney(val);

  const mut = useMutation({
    mutationFn: async () => {
      if (mode === "approve") return api.approve(m.id, notes.trim() || undefined);
      if (mode === "correct") return api.correct(m.id, parsed as number, notes.trim());
      return api.reject(m.id, notes.trim());
    },
    onSuccess: (r: { workflow_resumed: boolean; pending_remaining: number; adaptive?: { adjusted: { previous: number; new: number } | null } }) => {
      qc.invalidateQueries();
      const tuned = r.adaptive?.adjusted ? `Threshold auto-tuned based on reviewer feedback: ${r.adaptive.adjusted.previous}% → ${r.adaptive.adjusted.new}%. ` : "";
      onDone(`${tuned}${m.label} ${mode === "approve" ? "approved" : mode === "correct" ? "corrected" : "rejected"}. ${r.workflow_resumed ? "All mandatory items resolved — workflow resumed from its checkpoint." : `${r.pending_remaining} mandatory item(s) still pending in this audit.`}`);
      setMode(null); setNotes(""); setVal("");
    },
  });

  const needsNotes = mode === "correct" || mode === "reject";
  const valid = (!needsNotes || notes.trim().length > 0) && (mode !== "correct" || parsed !== null);
  const high = (m.confidence ?? 0) >= 98;

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-muted-foreground">{m.company} · FY{m.fiscal_year}</div>
          <h3 className="text-lg font-bold text-navy-900">{m.label}</h3>
        </div>
        <div className="text-right">
          <div className="num text-2xl font-bold text-navy-900" title={fullNumber(m.value)}>{m.found ? money(m.value, m.currency) : "MISSING"}</div>
          <div className="text-xs text-muted-foreground">period ending {m.period_end ?? "—"}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <div><div className="eyebrow">Extraction confidence</div>
          <div className="num mt-1 text-lg font-semibold">{m.confidence?.toFixed(1) ?? "—"}<span className="text-xs font-normal text-muted-foreground">/100</span></div>
          <Bar value={m.confidence ?? 0} tone={high ? "pass" : (m.confidence ?? 0) >= 90 ? "warn" : "danger"} /></div>
        <div><div className="eyebrow">Anomaly severity</div>
          <div className="mt-1 flex items-center gap-2"><StatusPill value={m.anomaly_status} />{m.anomaly_severity && <Badge>{m.anomaly_severity}</Badge>}</div>
          {m.anomaly_pct_change !== null && <div className="num mt-1 text-sm">{pct(m.anomaly_pct_change)} year over year</div>}</div>
        <div><div className="eyebrow">Validation / XBRL</div>
          <div className="mt-1 flex flex-wrap gap-1.5"><StatusPill value={m.validation_status} /><StatusPill value={m.xbrl_status} /></div></div>
      </div>

      {high && <Callout tone="gold" className="mt-4">Well-evidenced extraction, but <b>unsafe to approve automatically</b>: confidence is not approval.</Callout>}

      <div className="mt-4"><div className="eyebrow">Escalation reason</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{m.escalation_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        {m.anomaly_explanation && <p className="mt-1 text-xs text-muted-foreground">{m.anomaly_explanation}</p>}</div>

      <div className="mt-4"><div className="eyebrow">Evidence</div>
        <code className="mt-1 block whitespace-pre-wrap rounded-md border bg-secondary/60 p-2.5 text-xs">{m.snippet ?? "No source evidence (metric not found)."}</code>
        <div className="mt-1 text-xs text-muted-foreground">{m.location} · <Link className="font-semibold text-navy-600 hover:underline" to={`/audits/${m.workflow_id}/metrics/${m.id}`}>Open full evidence & explanation →</Link></div></div>

      <div className="mt-5 flex flex-wrap gap-2 border-t pt-4">
        <Button variant="pass" onClick={() => setMode("approve")}><Check className="h-4 w-4" />Approve</Button>
        <Button variant="warn" onClick={() => setMode("correct")}><FilePenLine className="h-4 w-4" />Correct</Button>
        <Button variant="danger" onClick={() => setMode("reject")}><X className="h-4 w-4" />Reject</Button>
      </div>

      <Dialog open={mode !== null} onOpenChange={(o) => { if (!o) { setMode(null); mut.reset(); } }}>
        <DialogContent>
          <DialogTitle className="capitalize">{mode} · {m.label}</DialogTitle>
          <DialogDescription>
            {mode === "approve" && "You accept the extracted value as reported. Your identity and timestamp are recorded in the append-only review history."}
            {mode === "correct" && "Provide the corrected value. The original extracted value is preserved; both are recorded with your notes."}
            {mode === "reject" && "Reject this extracted value. A reason is required and recorded permanently."}
          </DialogDescription>
          <div className="mt-4 space-y-4">
            <div className="rounded-md bg-secondary/60 p-3 text-sm">Original value: <b className="num">{money(m.value, m.currency)}</b> <span className="text-muted-foreground">({fullNumber(m.value)})</span></div>
            {mode === "correct" && (
              <div className="space-y-1.5"><Label htmlFor="cv">Corrected value (USD)</Label>
                <Input id="cv" value={val} onChange={(e) => setVal(e.target.value)} placeholder="e.g. 1,250,000,000 or 1250M or 1.25B" />
                {val && <div className="text-xs text-muted-foreground">{parsed === null ? "Not a valid amount." : `Interpreted as ${money(parsed, m.currency)} (${fullNumber(parsed)})`}</div>}</div>
            )}
            <div className="space-y-1.5"><Label htmlFor="rn">Reviewer notes {needsNotes ? <span className="text-danger">*required</span> : "(optional)"}</Label>
              <Textarea id="rn" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={needsNotes ? "Explain the basis for your decision…" : "Optional context…"} /></div>
            {mut.isError && <Callout tone="danger">{errMsg(mut.error)}</Callout>}
            <div className="flex justify-end gap-2">
              <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
              <Button variant={mode === "approve" ? "pass" : mode === "correct" ? "warn" : "danger"} disabled={!valid || mut.isPending} onClick={() => mut.mutate()}>
                {mut.isPending ? "Saving…" : `Confirm ${mode}`}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
