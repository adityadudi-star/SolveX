import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";
const KEY = "solvex-theme";

interface Ctx { theme: Theme; toggle: () => void; setTheme: (t: Theme) => void }
const ThemeContext = createContext<Ctx>({ theme: "light", toggle: () => {}, setTheme: () => {} });

const stored = (): Theme | null => {
  try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : null; } catch { return null; }
};
const system = (): Theme => (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");

function apply(t: Theme, animate: boolean) {
  const root = document.documentElement;
  // Instant swap (no global cross-fade): animating every element's colours could leave some stuck on the old theme.
  void animate;
  root.classList.remove("theme-transition");
  root.classList.toggle("dark", t === "dark");
  root.style.colorScheme = t;
  root.style.backgroundColor = t === "dark" ? "#060b1a" : "#cfe0f3";
}

/** Theme = saved choice (localStorage) → otherwise the OS preference, which is followed live until the user picks one. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => stored() ?? system());

  const setTheme = useCallback((t: Theme) => {
    apply(t, true);
    setThemeState(t);
    try { localStorage.setItem(KEY, t); } catch { /* private mode: still works for this session */ }
  }, []);
  const toggle = useCallback(() => setTheme(document.documentElement.classList.contains("dark") ? "light" : "dark"), [setTheme]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => { if (!stored()) { const t = e.matches ? "dark" : "light"; apply(t, true); setThemeState(t); } };
    const onStorage = (e: StorageEvent) => { if (e.key === KEY && (e.newValue === "light" || e.newValue === "dark")) { apply(e.newValue, true); setThemeState(e.newValue); } };
    mq.addEventListener("change", onChange);
    window.addEventListener("storage", onStorage); // keep several tabs in sync
    return () => { mq.removeEventListener("change", onChange); window.removeEventListener("storage", onStorage); };
  }, []);

  const value = useMemo(() => ({ theme, toggle, setTheme }), [theme, toggle, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
export const useTheme = () => useContext(ThemeContext);

/** Colours for recharts (which needs concrete values, not CSS variables). */
export function useChartColors() {
  const { theme } = useTheme();
  return theme === "dark"
    ? { grid: "#26345C", axis: "#8FA2CC", series: ["#7FA2F5", "#E3B341", "#4ADE80", "#FC8181"], empty: "#26345C" }
    : { grid: "#E2E8F0", axis: "#94A3B8", series: ["#12295C", "#C9971C", "#15803D", "#B91C1C"], empty: "#E2E8F0" };
}
