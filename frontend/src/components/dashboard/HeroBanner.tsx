import type { ReactNode } from "react";
import { HeroArt } from "@/components/HeroArt";
import { useReviewer } from "@/hooks/useReviewer";
import { useReveal } from "@/hooks/useReveal";

/** Overview hero: greeting, tagline, primary action and the animated SVG illustration. */
export function HeroBanner({ subtitle, action }: { subtitle: ReactNode; action: ReactNode }) {
  const { session } = useReviewer();
  const ref = useReveal<HTMLElement>();
  return (
    <section ref={ref} aria-labelledby="overview-title" className="card-glass relative mb-6 overflow-hidden rounded-xl border p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-gold-400/20 blur-3xl" aria-hidden="true" />
      <div className="relative grid items-center gap-6 md:grid-cols-[1.3fr_1fr]">
        <div>
          <div className="eyebrow">Financial Auditor</div>
          <h1 id="overview-title" className="mt-1 text-3xl font-extrabold text-navy-900 sm:text-4xl">
            Welcome back{session?.name ? <>, <span className="bg-gradient-to-r from-gold-400 to-gold-600 bg-clip-text text-transparent">{session.name}</span></> : null}
          </h1>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">{subtitle}</p>
          <p className="mt-1 max-w-lg text-sm font-medium text-navy-700">Extract the Facts. Investigate the Trust.</p>
          <div className="mt-5 flex flex-wrap items-center gap-2">{action}</div>
        </div>
        <HeroArt className="mx-auto hidden w-full max-w-sm md:block" />
      </div>
    </section>
  );
}
