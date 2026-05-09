import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "var(--bg)",
          secondary: "var(--bg-secondary)",
        },
        card: {
          DEFAULT: "var(--card)",
          inner: "var(--card-inner)",
        },
        sidebar: {
          bg: "var(--sidebar-bg)",
        },
        border: {
          DEFAULT: "var(--border)",
          light: "var(--border-light)",
        },
        text: {
          DEFAULT: "var(--text)",
          secondary: "var(--text-secondary)",
        },
        muted: "var(--muted)",
        accent: {
          DEFAULT: "var(--accent)",
          glow: "var(--accent-glow)",
        },
        cyan: "var(--cyan)",
        green: {
          DEFAULT: "var(--green)",
          dim: "var(--green-dim)",
        },
        red: {
          DEFAULT: "var(--red)",
          dim: "var(--red-dim)",
        },
        yellow: "var(--yellow)",
        purple: {
          DEFAULT: "var(--purple)",
          dim: "var(--purple-dim)",
        },
        // Workstation aesthetic (Variation C) — additive namespace so the
        // existing Linear palette above stays intact while Stage 2+ migrates
        // components onto these. Use as `bg-tm-bg`, `text-tm-fg`, `border-tm-rule`,
        // `text-tm-accent`, etc.
        tm: {
          bg: "var(--tm-bg)",
          "bg-2": "var(--tm-bg-2)",
          "bg-3": "var(--tm-bg-3)",
          fg: "var(--tm-fg)",
          "fg-2": "var(--tm-fg-2)",
          muted: "var(--tm-muted)",
          rule: "var(--tm-rule)",
          "rule-2": "var(--tm-rule-2)",
          accent: "var(--tm-accent)",
          "accent-soft": "var(--tm-accent-soft)",
          warn: "var(--tm-warn)",
          "warn-soft": "var(--tm-warn-soft)",
          neg: "var(--tm-neg)",
          "neg-soft": "var(--tm-neg-soft)",
          info: "var(--tm-info)",
          pos: "var(--tm-pos)",
        },
      },
      fontFamily: {
        sans: [
          "Songti SC",
          "Source Han Serif SC",
          "Noto Serif CJK SC",
          "STSong",
          "SimSun",
          "Inter Variable",
          "Inter",
          "-apple-system",
          "serif",
        ],
        mono: ["SF Mono", "Fira Code", "monospace"],
        // Workstation primary — JetBrains Mono. Loaded via next/font in
        // app/layout.tsx so the font CSS var resolves to the correct
        // self-hosted asset (no FOUT, no Google Fonts request at runtime).
        // Use as `font-tm-mono` on a workstation pane root.
        "tm-mono": [
          "var(--font-jetbrains-mono)",
          "JetBrains Mono",
          "SF Mono",
          "IBM Plex Mono",
          "ui-monospace",
          "monospace",
        ],
        "tm-sans": [
          "var(--font-inter-tight)",
          "Inter Tight",
          "system-ui",
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "12px",
      },
      animation: {
        pulse: "pulse 2s ease-in-out infinite",
        // Workstation status LEDs and decay-bar fills.
        "tm-pulse": "tm-pulse 1.4s ease-in-out infinite",
      },
      keyframes: {
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        // tm-pulse keyframes are defined in globals.css alongside the
        // --tm-* token block so the animation reads identically whether
        // a component uses tw class or raw CSS.
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
  ],
};

export default config;
