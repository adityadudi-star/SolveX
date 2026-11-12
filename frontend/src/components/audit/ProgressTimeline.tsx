import { CheckCircle2, Circle, Loader2, PauseCircle, XCircle } from "lucide-react";
import type { StageView } from "@/types";
import { cn } from "@/utils/cn";

const ICON = {
  completed: <CheckCircle2 className="h-5 w-5 text-pass" />,
  running: <Loader2 className="h-5 w-5 animate-spin text-navy-600" />,
  paused: <PauseCircle className="h-5 w-5 text-danger" />,
  failed: <XCircle className="h-5 w-5 text-danger" />,
  pending: <Circle className="h-5 w-5 text-muted-foreground/40" />,
};

export function ProgressTimeline({ stages, transport }: { stages: StageView[]; transport?: string | null }) {
  const done = stages.filter((s) => s.state === "completed").length;
  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>{done} of {stages.length} stages complete</span>
        {transport && <span className="rounded bg-secondary px-1.5 py-0.5 uppercase tracking-wide">live · {transport}</span>}
      </div>
      <ol className="relative space-y-0">
        {stages.map((s, i) => (
          <li key={s.stage} className="relative flex gap-3 pb-4 last:pb-0">
            {i < stages.length - 1 && <span className={cn("absolute left-[9.5px] top-6 h-[calc(100%-1.25rem)] w-px", s.state === "completed" ? "bg-pass/40" : "bg-border")} />}
            <span className="z-10 mt-0.5 rounded-full bg-white">{ICON[s.state]}</span>
            <div className="min-w-0">
              <div className={cn("text-sm font-medium", s.state === "pending" && "text-muted-foreground")}>{s.label}</div>
              {s.message && s.state !== "pending" && <div className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{s.message}</div>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
