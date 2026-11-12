import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Trends } from "@/types";
import { money } from "@/utils/format";

const COLORS = ["#12295C", "#C9971C", "#15803D", "#B91C1C"];

function merge(t: Trends, keys: string[]) {
  const years = new Set<number>();
  keys.forEach((k) => t.series[k]?.points.forEach((p) => years.add(p.year)));
  return [...years].sort().map((y) => {
    const row: Record<string, number | null> = { year: y };
    keys.forEach((k) => { row[k] = t.series[k]?.points.find((p) => p.year === y)?.value ?? null; });
    return row;
  });
}

export function TrendChart({ trends, keys, kind = "line" }: { trends: Trends; keys: string[]; kind?: "line" | "bar" }) {
  const present = keys.filter((k) => trends.series[k]);
  if (present.length === 0) return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">No stored data for this chart.</div>;
  const data = merge(trends, present);
  const common = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
      <XAxis dataKey="year" tick={{ fontSize: 12 }} stroke="#94A3B8" />
      <YAxis tickFormatter={(v) => money(v).replace("$", "")} tick={{ fontSize: 12 }} stroke="#94A3B8" width={64} />
      <Tooltip formatter={(v: number, n: string) => [money(v), trends.series[n]?.label ?? n]} />
      <Legend formatter={(n) => trends.series[n as string]?.label ?? n} />
    </>
  );
  return (
    <div className="h-72">
      <ResponsiveContainer>
        {kind === "bar" ? (
          <BarChart data={data}>{common}{present.map((k, i) => <Bar key={k} dataKey={k} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} />)}</BarChart>
        ) : (
          <LineChart data={data}>{common}{present.map((k, i) => <Line key={k} dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5} dot={{ r: 4 }} connectNulls />)}</LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
