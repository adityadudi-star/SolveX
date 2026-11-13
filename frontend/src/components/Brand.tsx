import { cn } from "@/utils/cn";
import { useTheme } from "@/hooks/useTheme";

/** Full SolveX logo. Optimised WebP (≈38 KB vs 196 KB PNG) with a light-ink variant for dark mode; explicit size avoids layout shift. */
export function Logo({ className, priority }: { className?: string; priority?: boolean }) {
  const { theme } = useTheme();
  return (
    <img src={theme === "dark" ? "/solvex-logo-dark.webp" : "/solvex-logo.webp"} width={640} height={155}
      alt="SolveX — Agentic AI | Autonomous Workflows" className={cn("h-auto w-40 select-none", className)} draggable={false}
      decoding="async" loading={priority ? "eager" : "lazy"} {...(priority ? ({ fetchpriority: "high" } as Record<string, string>) : {})} />
  );
}
export function LogoMark({ className }: { className?: string }) {
  const { theme } = useTheme();
  return <img src={theme === "dark" ? "/solvex-mark-dark.webp" : "/solvex-mark.webp"} width={192} height={192} alt="SolveX" className={cn("h-9 w-9 select-none", className)} draggable={false} decoding="async" />;
}

export function SplashScreen({ label = "Loading SolveX…" }: { label?: string }) {
  const { theme } = useTheme();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-background" role="status" aria-live="polite">
      <img src={theme === "dark" ? "/solvex-mark-dark.webp" : "/solvex-mark.webp"} width={192} height={192} alt="" className="solvex-pulse h-20 w-20" />
      <div className="text-center">
        <div className="text-sm font-semibold text-navy-800">{label}</div>
        <div className="mt-1 text-xs text-muted-foreground">Extract the Facts. Investigate the Trust.</div>
      </div>
    </div>
  );
}
