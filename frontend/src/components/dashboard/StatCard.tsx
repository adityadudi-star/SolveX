import type { ReactNode } from "react";
import { Card } from "@/components/ui/primitives";
import { cn } from "@/utils/cn";

export function StatCard({ label, value, icon, tone = "navy", hint }: { label: string; value: ReactNode; icon: ReactNode; tone?: "navy" | "pass" | "warn" | "danger" | "gold"; hint?: string }) {
  const t = { navy: "bg-navy-50 text-navy-700", pass: "bg-pass-soft text-pass", warn: "bg-warn-soft text-warn", danger: "bg-danger-soft text-danger", gold: "bg-gold-50 text-gold-600" }[tone];
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="eyebrow">{label}</div>
          <div className="num mt-1.5 text-3xl font-bold text-navy-900">{value}</div>
          {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
        </div>
        <div className={cn("rounded-lg p-2", t)}>{icon}</div>
      </div>
    </Card>
  );
}
