import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Paleta Kitou (manual Pulso): Tinta #0E0F1A, Limão #C6F432, Violeta #7B61FF, Gelo #F4F5F0, Grafite #5A5F73.
           Limão é o sinal de "pago" e a ação principal; Violeta é apoio; texto em Tinta ou branco, Grafite só auxiliar. */
        ink: {
          950: "#0e0f1a",
          900: "#0e0f1a",
          800: "#23263a",
          700: "#5a5f73",
        },
        paper: {
          50: "#f4f5f0",
          100: "#ebede5",
          200: "#dfe1d8",
        },
        brand: {
          700: "#5b43e6",
          600: "#6a52f5",
          500: "#7b61ff",
          300: "#b5a6ff",
          100: "#ece8ff",
        },
        /* Superfícies escuras do site (landing e /entrar): entrada do painel e menu lateral. */
        night: {
          950: "#0e0f1a",
          900: "#121423",
          800: "#161829",
          700: "#1c1f32",
          field: "#10121e",
          fg: "#f4f5f0",
          muted: "#a0a4b5",
          dim: "#6e7387",
        },
        signal: {
          500: "#b4e01f",
          400: "#c6f432",
          100: "#eefbc6",
        },
      },
      fontFamily: {
        display: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        mark: ["var(--font-mark)", "var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(14, 15, 26, 0.05), 0 12px 32px -18px rgba(14, 15, 26, 0.2)",
      },
    },
  },
  plugins: [],
};

export default config;
