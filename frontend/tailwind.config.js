/** @type {import('tailwindcss').Config} */
export default {
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
        navy: { 50: "#F1F4FA", 100: "#E1E7F3", 200: "#C3CFE6", 600: "#1B3A7A", 700: "#12295C", 800: "#0D1F4A", 900: "#0A1838" },
        gold: { 50: "#FBF6E6", 100: "#F5E9BF", 400: "#D9AE35", 500: "#C9971C", 600: "#A97B12" },
        pass: { DEFAULT: "#15803D", soft: "#E8F5EC" },
        warn: { DEFAULT: "#B45309", soft: "#FEF3E2" },
        danger: { DEFAULT: "#B91C1C", soft: "#FDECEC" },
      },
      borderRadius: { lg: "0.75rem", md: "0.5rem", sm: "0.375rem" },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"] },
      boxShadow: { card: "0 1px 2px rgba(10,24,56,0.04), 0 4px 16px rgba(10,24,56,0.05)" },
    },
  },
  plugins: [],
};
