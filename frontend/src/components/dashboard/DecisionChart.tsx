import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { DecisionCode } from "@/types";
import { DECISION } from "@/utils/format";

export const DECISION_COLORS: Record<DecisionCode, string> = {
  FULLY_PASSED: "#15803D",
  PASSED_HUMAN_CONSIDERATION_RECOMMENDED: "#B45309",
  HUMAN_APPROVAL_REQUIRED: "#B91C1C",
};

export function DecisionChart({ data }: { data: Record<DecisionCode, number> }) {
  const rows = (Object.keys(DECISION) as DecisionCode[]).map((k) => ({ key: k, name: DECISION[k].label, value: data[k] ?? 0 }));
  const total = rows.reduce((a, r) => a + r.value, 0);
  return (
    <div>
      <div className="relative h-52">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={total ? rows : [{ key: "none", name: "No data", value: 1 }]} dataKey="value" innerRadius={58} outerRadius={84} paddingAngle={total ? 2 : 0} stroke="none">
              {total ? rows.map((r) => <Cell key={r.key} fill={DECISION_COLORS[r.key]} />) : <Cell fill="#E2E8F0" />}
            </Pie>
            {total > 0 && <Tooltip formatter={(v: number, n: string) => [v, n]} />}
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="num text-3xl font-bold text-navy-900">{total}</div>
          <div className="text-[11px] text-muted-foreground">decisions</div>
        </div>
      </div>
      <ul className="mt-2 space-y-1.5 text-sm">
        {rows.map((r) => (
          <li key={r.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: DECISION_COLORS[r.key] }} />{r.name}</span>
            <span className="num font-semibold">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
