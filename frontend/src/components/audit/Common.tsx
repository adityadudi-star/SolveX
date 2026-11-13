import type { ReactNode } from "react";
import { Info } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { cn } from "@/utils/cn";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-2 px-6 py-14 text-center">
      <img src="/solvex-mark.png" alt="" className="h-12 w-12 opacity-80" />
      <div className="text-base font-semibold text-navy-800">{title}</div>
      {body && <div className="max-w-md text-sm text-muted-foreground">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </Card>
  );
}

export function Callout({ tone = "navy", icon, title, children, className }: { tone?: "navy" | "warn" | "danger" | "pass" | "gold"; icon?: ReactNode; title?: string; children: ReactNode; className?: string }) {
  const t = {
    navy: "border-navy-200 bg-navy-50 text-navy-800", warn: "border-warn-line bg-warn-soft text-warn-ink",
    danger: "border-danger-line bg-danger-soft text-danger-ink", pass: "border-pass-line bg-pass-soft text-pass-ink", gold: "border-gold-100 bg-gold-50 text-navy-900",
  }[tone];
  return (
    <div className={cn("flex gap-3 rounded-lg border p-4 text-sm", t, className)}>
      <span className="mt-0.5 shrink-0">{icon ?? <Info className="h-4 w-4" />}</span>
      <div>{title && <div className="font-semibold">{title}</div>}<div className={title ? "mt-0.5 opacity-90" : ""}>{children}</div></div>
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return <Callout tone="danger" title="Something went wrong">{message}</Callout>;
}
