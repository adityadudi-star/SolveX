import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileSearch, Lock, ShieldCheck, UserCheck } from "lucide-react";
import { Logo } from "@/components/Brand";
import { Backdrop } from "@/components/Backdrop";
import { HeroArt } from "@/components/HeroArt";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button, Card, CardContent, Input, Label } from "@/components/ui/primitives";
import { Callout } from "@/components/audit/Common";
import { api, errMsg } from "@/services/api";
import { useReviewer } from "@/hooks/useReviewer";

const POINTS = [
  [FileSearch, "Real SEC filings", "10-K data with source evidence for every number."],
  [ShieldCheck, "Verified against XBRL", "Deterministic checks. Nothing is ever fabricated."],
  [UserCheck, "Human in the loop", "Risky values pause for a reviewer, always."],
] as const;

export default function Login() {
  const { login } = useReviewer();
  const [name, setName] = useState("Priyanshu");
  const [token, setToken] = useState("");
  const m = useMutation({
    mutationFn: () => api.login(name.trim(), token),
    onSuccess: () => login({ name: name.trim(), token }),
  });

  return (
    <div className="relative min-h-screen">
      <Backdrop />
      <div className="absolute right-4 top-4 z-10 sm:right-8 sm:top-6"><ThemeToggle /></div>
      <main id="main" className="mx-auto grid min-h-screen w-full max-w-6xl items-center gap-10 px-4 py-16 lg:grid-cols-[1.1fr_1fr] lg:gap-14">
        <section className="page-enter text-center lg:text-left" aria-labelledby="hero-title">
          <Logo className="mx-auto w-60 sm:w-72 lg:mx-0" priority />
          <h1 id="hero-title" className="mt-6 text-3xl font-extrabold leading-tight text-navy-900 sm:text-4xl">
            Extract the Facts.<br /><span className="bg-gradient-to-r from-gold-400 to-gold-600 bg-clip-text text-transparent">Investigate the Trust.</span>
          </h1>
          <p className="mx-auto mt-3 max-w-md text-sm text-muted-foreground lg:mx-0">An intelligent human-in-the-loop financial filing auditing platform.</p>
          <HeroArt className="mx-auto mt-6 hidden w-full max-w-md sm:block lg:max-w-lg" />
          <ul className="mx-auto mt-6 grid max-w-xl gap-3 text-left sm:grid-cols-3 lg:mx-0">
            {POINTS.map(([Icon, t, d], i) => (
              <li key={t} className="card-glass card-hover rounded-lg border p-3 animate-fade-up" style={{ animationDelay: `${150 + i * 90}ms` }}>
                <Icon className="icon-pop h-4 w-4 text-gold-600" aria-hidden="true" />
                <div className="mt-1.5 text-sm font-semibold text-navy-800">{t}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{d}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="animate-fade-up mx-auto w-full max-w-md" style={{ animationDelay: "120ms" }} aria-label="Sign in">
          <Card>
            <CardContent className="p-6 sm:p-7">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-navy-900"><Lock className="h-4 w-4 text-gold-600" aria-hidden="true" />Reviewer sign-in</h2>
              <form className="mt-4 space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
                <div className="space-y-1.5"><Label htmlFor="n">Your name (recorded in the review history)</Label>
                  <Input id="n" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ada Reviewer" autoFocus minLength={2} required autoComplete="username" /></div>
                <div className="space-y-1.5"><Label htmlFor="t">Demo reviewer token</Label>
                  <Input id="t" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="REVIEWER_TOKEN from backend/.env" required autoComplete="current-password" /></div>
                {m.isError && <div role="alert"><Callout tone="danger">{errMsg(m.error)}</Callout></div>}
                <Button className="w-full" size="lg" disabled={m.isPending}>{m.isPending ? "Checking…" : "Sign in"}</Button>
              </form>
              <Callout tone="warn" className="mt-5" title="Demo authentication">
                A shared token protects reviewer actions in this prototype. It is not production-grade authentication (no per-user credentials, MFA, or session management).
              </Callout>
            </CardContent>
          </Card>
          <p className="mt-6 text-center text-xs text-muted-foreground">© SolveX · SolveX Financial Auditor</p>
        </section>
      </main>
    </div>
  );
}
