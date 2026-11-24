import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        synapse: {
          bg: "var(--background)",
          surface: "var(--surface)",
          raised: "var(--surface-raised)",
          hover: "var(--surface-hover)",
          active: "var(--surface-active)",
          border: "var(--border)",
          "border-subtle": "var(--border-subtle)",
          "border-strong": "var(--border-strong)",
          text: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
          accent: "var(--accent)",
          "accent-hover": "var(--accent-hover)",
          "accent-subtle": "var(--accent-subtle)",
          warm: "var(--accent-warm)",
          "warm-subtle": "var(--accent-warm-subtle)",
          success: "var(--success)",
          warning: "var(--warning)",
          danger: "var(--danger)",
        },
        primary: {
          50: "#f0f5ff",
          100: "#e0ebff",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Inter"',
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          '"Fira Code"',
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        subtle: "0 1px 2px 0 rgba(0, 0, 0, 0.25)",
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.4)",
        composer: "0 8px 32px -4px rgba(0, 0, 0, 0.5)",
      },
    },
  },
  plugins: [],
};
export default config;
