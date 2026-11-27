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
        primary: {
          50: "#f2f0ff",
          100: "#e8e5ff",
          500: "#a49aff",
          600: "#8e83ea",
          700: "#7168bd",
        },
      },
    },
  },
  plugins: [],
};
export default config;
