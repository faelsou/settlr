import { QueryProvider } from "@/lib/query";
import { SentryClient } from "@/lib/sentry-client";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/sora/latin-600.css";
import "@fontsource/sora/latin-700.css";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Settlr",
  description: "Painel do operador — exceções, pagamentos, títulos e o agente de WhatsApp.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head />
      <body>
        <SentryClient />
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
