/** @type {import('tailwindcss').Config} */
// Colours are CSS variables (RGB triplets) so the whole UI re-themes by swapping variables (see src/index.css).
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        surface: v("surface"),
        overlay: v("overlay"),
        brand: { DEFAULT: v("brand"), hover: v("brand-hover") },
        navy: { 50: v("navy-50"), 100: v("navy-100"), 200: v("navy-200"), 600: v("navy-600"), 700: v("navy-700"), 800: v("navy-800"), 900: v("navy-900") },
        gold: { 50: v("gold-50"), 100: v("gold-100"), 400: v("gold-400"), 500: v("gold-500"), 600: v("gold-600") },
        pass: { DEFAULT: v("pass"), soft: v("pass-soft"), fg: v("pass-fg"), line: v("pass-line"), ink: v("pass-ink") },
        warn: { DEFAULT: v("warn"), soft: v("warn-soft"), fg: v("warn-fg"), line: v("warn-line"), ink: v("warn-ink") },
        danger: { DEFAULT: v("danger"), soft: v("danger-soft"), fg: v("danger-fg"), line: v("danger-line"), ink: v("danger-ink") },
      },
      borderRadius: { lg: "0.75rem", md: "0.5rem", sm: "0.375rem" },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"] },
      boxShadow: {
        glow: "0 0 0 1px rgba(201,151,28,0.35), 0 6px 28px rgba(201,151,28,0.22)",
        "glow-navy": "0 0 22px rgba(27,58,122,0.35)",
        card: "0 1px 2px rgba(10,24,56,0.04), 0 4px 16px rgba(10,24,56,0.05)",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(12px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { "fade-up": "fade-up .5s cubic-bezier(.22,1,.36,1) backwards" },
    },
  },
  plugins: [],
};
