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
      },
      borderRadius: {
        card: "12px",
      },
      animation: {
        pulse: "pulse 2s ease-in-out infinite",
      },
      keyframes: {
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
  ],
};

export default config;
