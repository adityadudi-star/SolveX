import { useState } from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ClipboardCheck, History, Info, LayoutDashboard, LogOut, Menu, PlayCircle, Settings, ShieldCheck, TrendingUp, X } from "lucide-react";
import { Logo } from "@/components/Brand";
import { api } from "@/services/api";
import { useReviewer } from "@/hooks/useReviewer";
import { cn } from "@/utils/cn";
import { Button } from "@/components/ui/primitives";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/audits/new", label: "New Audit", icon: PlayCircle },
  { to: "/reviews", label: "Human Review", icon: ClipboardCheck, badge: true },
  { to: "/trends", label: "Historical Analysis", icon: TrendingUp },
  { to: "/audits", label: "Audit History", icon: History, end: true },
  { to: "/settings", label: "Settings & Observability", icon: Settings },
  { to: "/about", label: "About", icon: Info },
];

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const { session, logout } = useReviewer();
  const { data } = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: 8000 });
  const pending = data?.pending_reviews ?? 0;

  const sidebar = (
    <div className="flex h-full flex-col">
      <Link to="/" className="block px-5 pb-4 pt-5" onClick={() => setOpen(false)}><Logo className="w-44" /></Link>
      <div className="px-5 pb-3 text-[11px] leading-snug text-muted-foreground">Financial Auditor · <span className="font-medium text-navy-700">Extract the Facts. Investigate the Trust.</span></div>
      <nav className="flex-1 space-y-0.5 px-3" aria-label="Primary">
        {NAV.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
            className={({ isActive }) => cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-navy-800/80 transition-colors hover:bg-navy-50",
              isActive && "bg-navy-800 text-white hover:bg-navy-800")}>
            <Icon className="h-4 w-4" /> <span className="flex-1">{label}</span>
            {badge && pending > 0 && <span className="rounded-full bg-danger px-2 py-0.5 text-[10px] font-bold text-white">{pending}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-lg border bg-secondary/60 p-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-navy-800"><ShieldCheck className="h-4 w-4 text-gold-600" />Reviewer</div>
        <div className="mt-1 truncate text-sm">{session?.name}</div>
        <div className="mt-0.5 text-[10px] text-muted-foreground">Demo authentication — not production-grade.</div>
        <Button variant="outline" size="sm" className="mt-2 w-full" onClick={logout}><LogOut className="h-3.5 w-3.5" />Sign out</Button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17rem_1fr]">
      <aside className="sticky top-0 hidden h-screen border-r bg-white lg:block">{sidebar}</aside>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b bg-white px-4 py-2 lg:hidden">
        <Link to="/"><Logo className="w-32" /></Link>
        <Button variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></Button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-900/40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-72 bg-white shadow-xl">
            <Button variant="ghost" size="icon" className="absolute right-2 top-2" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-4 w-4" /></Button>
            {sidebar}
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"><Outlet /></main>
        <footer className="border-t bg-white px-6 py-4 text-xs text-muted-foreground">
          <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5 text-gold-600" /><b className="text-navy-800">SolveX</b> Financial Auditor · An intelligent human-in-the-loop financial filing auditing platform.</span>
            <span>Prototype decision-support tool — not an audit opinion. Thresholds are demonstration defaults.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
