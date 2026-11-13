import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/utils/cn";

/** Animated light/dark switch. A real <button role="switch"> so it works with keyboard and screen readers. */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button type="button" role="switch" aria-checked={dark} aria-label="Dark mode" title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggle} className={cn("theme-toggle", className)}>
      <span className="thumb" aria-hidden="true" />
      <Sun className="sun" aria-hidden="true" />
      <Moon className="moon" aria-hidden="true" />
    </button>
  );
}
