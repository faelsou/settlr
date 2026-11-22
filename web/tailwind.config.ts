import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#12101f",
          900: "#12101f",
          800: "#26223d",
          700: "#5f5a78",
        },
        paper: {
          50: "#f7f6fc",
          100: "#eeeafe",
          200: "#e3def7",
        },
        brand: {
          700: "#5b3df5",
          600: "#4b2fe0",
          500: "#7c5cff",
          300: "#b7a8ff",
          100: "#eeeafe",
        },
        /* Superfícies escuras do site (landing e /entrar): entrada do painel e menu lateral. */
        night: {
          950: "#09080f",
          900: "#0e0c18",
          800: "#12101f",
          700: "#171429",
          field: "#0d0b17",
          fg: "#f4f2ff",
          muted: "#9b96b6",
          dim: "#6c6789",
        },
        signal: {
          400: "#c6f432",
          100: "#f1fccb",
        },
      },
      fontFamily: {
        display: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        mark: ["var(--font-mark)", "var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(18, 16, 31, 0.05), 0 12px 32px -18px rgba(18, 16, 31, 0.2)",
      },
    },
  },
  plugins: [],
};

export default config;
