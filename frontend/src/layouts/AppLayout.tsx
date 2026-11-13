import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, Brain, ClipboardCheck, History, Info, LayoutDashboard, LogOut, Menu, PlayCircle, Settings, ShieldCheck, TrendingUp, X } from "lucide-react";
import { Logo } from "@/components/Brand";
import { Backdrop } from "@/components/Backdrop";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api } from "@/services/api";
import { useReviewer } from "@/hooks/useReviewer";
import { cn } from "@/utils/cn";
import { Button } from "@/components/ui/primitives";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/audits/new", label: "New Audit", icon: PlayCircle },
  { to: "/reviews", label: "Human Review", icon: ClipboardCheck, badge: true },
  { to: "/adaptive", label: "Adaptive Thresholds", icon: Brain },
  { to: "/trends", label: "Historical Analysis", icon: TrendingUp },
  { to: "/audits", label: "Audit History", icon: History, end: true },
  { to: "/settings", label: "Settings & Observability", icon: Settings },
  { to: "/about", label: "About", icon: Info },
];

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const { session, logout } = useReviewer();
  const { pathname } = useLocation();
  const closeBtn = useRef<HTMLButtonElement>(null);
  const menuBtn = useRef<HTMLButtonElement>(null);
  const { data } = useQuery({ queryKey: ["summary"], queryFn: api.summary, refetchInterval: 8000 });
  const pending = data?.pending_reviews ?? 0;

  // Mobile drawer: Escape closes, body scroll is locked, focus moves in and returns to the menu button.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeBtn.current?.focus();
    const btn = menuBtn.current;
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; btn?.focus(); };
  }, [open]);

  // New page → start at the top (smooth page transition is the keyed wrapper below).
  useEffect(() => { window.scrollTo({ top: 0 }); }, [pathname]);

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 px-5 pb-4 pt-5">
        <Link to="/" className="block" onClick={() => setOpen(false)} aria-label="SolveX home"><Logo className="w-40" priority /></Link>
      </div>
      <div className="px-5 pb-3 text-[11px] leading-snug text-muted-foreground">Financial Auditor · <span className="font-medium text-navy-700">Extract the Facts. Investigate the Trust.</span></div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3" aria-label="Primary">
        {NAV.map(({ to, label, icon: Icon, end, badge }) => (
          <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
            className={({ isActive }) => cn("nav-link group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-navy-800/80 transition-all hover:bg-navy-50 hover:pl-4",
              isActive && "bg-brand pl-4 text-white hover:bg-brand shadow-sm")}>
            <Icon className="h-4 w-4 transition-transform duration-300 group-hover:scale-110" aria-hidden="true" /> <span className="flex-1">{label}</span>
            {badge && pending > 0 && <span className="rounded-full bg-danger px-2 py-0.5 text-[10px] font-bold text-white" aria-label={`${pending} pending`}>{pending}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-lg border bg-secondary/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-navy-800"><ShieldCheck className="h-4 w-4 text-gold-600" aria-hidden="true" />Reviewer</div>
          <ThemeToggle />
        </div>
        <div className="mt-1 truncate text-sm font-semibold">{session?.name}</div>
        <div className="truncate text-[11px] text-gold-600">@{(session?.name ?? "").toLowerCase().replace(/\s+/g, "")}</div>
        <div className="mt-0.5 text-[10px] text-muted-foreground">Demo authentication — not production-grade.</div>
        <Button variant="outline" size="sm" className="mt-2 w-full" onClick={logout}><LogOut className="h-3.5 w-3.5" />Sign out</Button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[17rem_1fr]">
      <Backdrop />
      <a href="#main" className="skip-link">Skip to main content</a>
      <aside className="sticky top-0 hidden h-screen border-r bg-surface lg:block">{sidebar}</aside>
      <header className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b bg-surface px-4 py-2 lg:hidden">
        <Link to="/" aria-label="SolveX home"><Logo className="w-32" priority /></Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button ref={menuBtn} variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} aria-controls="mobile-menu"><Menu className="h-5 w-5" /></Button>
        </div>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div className="fade-enter absolute inset-0 bg-overlay/50 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <div id="mobile-menu" className="drawer-enter absolute left-0 top-0 h-full w-72 max-w-[85vw] border-r bg-surface shadow-xl">
            <Button ref={closeBtn} variant="ghost" size="icon" className="absolute right-2 top-2 z-10" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-4 w-4" /></Button>
            {sidebar}
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-col">
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 outline-none sm:px-6 lg:px-8 lg:py-8">
          <div key={pathname} className="page-enter"><Outlet /></div>
        </main>
        <footer className="border-t bg-surface/80 px-6 py-5 text-xs text-muted-foreground backdrop-blur">
          <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5 text-gold-600" aria-hidden="true" /><b className="text-navy-800">SolveX</b> Financial Auditor · An intelligent human-in-the-loop financial filing auditing platform.</span>
            <span>Prototype decision-support tool — not an audit opinion. Thresholds are demonstration defaults.</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
