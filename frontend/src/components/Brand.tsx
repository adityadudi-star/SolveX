import { cn } from "@/utils/cn";

/** Full SolveX logo (uses the supplied brand asset). */
export function Logo({ className }: { className?: string }) {
  return <img src="/solvex-logo.png" alt="SolveX — Agentic AI | Autonomous Workflows" className={cn("h-auto w-40 select-none", className)} draggable={false} />;
}
export function LogoMark({ className }: { className?: string }) {
  return <img src="/solvex-mark.png" alt="SolveX" className={cn("h-9 w-9 select-none", className)} draggable={false} />;
}

export function SplashScreen({ label = "Loading SolveX…" }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-background" role="status" aria-live="polite">
      <img src="/solvex-mark.png" alt="" className="solvex-pulse h-20 w-20" />
      <div className="text-center">
        <div className="text-sm font-semibold text-navy-800">{label}</div>
        <div className="mt-1 text-xs text-muted-foreground">Extract the Facts. Investigate the Trust.</div>
      </div>
    </div>
  );
}
