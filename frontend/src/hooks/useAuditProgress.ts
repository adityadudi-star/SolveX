import { useEffect, useRef, useState } from "react";
import { API_BASE, api } from "@/services/api";
import type { ProgressSnapshot, StageView } from "@/types";

/** Streams REAL backend progress events over Server-Sent Events; falls back to polling if SSE is unavailable. */
export function useAuditProgress(workflowId: string | null) {
  const [snap, setSnap] = useState<ProgressSnapshot | null>(null);
  const [log, setLog] = useState<{ id: number; stage: string; message: string; ts: string; status: string }[]>([]);
  const [transport, setTransport] = useState<"sse" | "polling" | null>(null);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    if (!workflowId) return;
    setSnap(null); setLog([]); seen.current = new Set();
    let es: EventSource | null = null;
    let poll: number | undefined;
    let closed = false;

    const startPolling = () => {
      setTransport("polling");
      const tick = async () => {
        try {
          const s = await api.progress(workflowId);
          if (closed) return;
          setSnap(s);
          if (["completed", "failed", "awaiting_review"].includes(s.status)) return;
        } catch { /* keep trying */ }
        poll = window.setTimeout(tick, 1200);
      };
      tick();
    };

    try {
      es = new EventSource(`${API_BASE}/audits/${workflowId}/progress`);
      setTransport("sse");
      es.addEventListener("progress", (ev) => {
        const d = JSON.parse((ev as MessageEvent).data);
        setSnap({ status: d.status, current_stage: d.current_stage, error: d.error, stages: d.stages as StageView[] });
        if (!seen.current.has(d.id)) {
          seen.current.add(d.id);
          setLog((l) => [...l, { id: d.id, stage: d.stage, message: d.message, ts: d.ts, status: d.event_status }]);
        }
      });
      es.addEventListener("end", (ev) => {
        const d = JSON.parse((ev as MessageEvent).data);
        setSnap({ status: d.status, current_stage: d.current_stage, error: d.error, stages: d.stages });
        es?.close();
      });
      es.onerror = () => { es?.close(); if (!closed) startPolling(); };
    } catch { startPolling(); }

    return () => { closed = true; es?.close(); if (poll) clearTimeout(poll); };
  }, [workflowId]);

  return { snap, log, transport };
}
