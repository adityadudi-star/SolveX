import { useLayoutEffect, useRef } from "react";

/* One shared IntersectionObserver for every revealed element (cheap, no per-element observers). */
let observer: IntersectionObserver | null = null;
const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function getObserver() {
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) { e.target.classList.add("is-visible"); observer?.unobserve(e.target); }
        }
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.08 },
    );
  }
  return observer;
}

/** Adds `.reveal` and reveals the element once it scrolls into view. `delay` (ms) staggers siblings. */
export function useReveal<T extends HTMLElement>(delay = 0) {
  const ref = useRef<T>(null);
  useLayoutEffect(() => { // before paint: no flash of un-hidden content
    const el = ref.current;
    if (!el) return;
    if (reduced() || typeof IntersectionObserver === "undefined") { el.classList.add("is-visible"); return; }
    if (delay) el.style.setProperty("--d", `${delay}ms`);
    el.classList.add("reveal");
    const o = getObserver();
    o.observe(el);
    return () => o.unobserve(el); // no leaked observers when the element unmounts
  }, [delay]);
  return ref;
}
