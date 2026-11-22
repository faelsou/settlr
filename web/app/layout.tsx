import { I18nProvider } from "@/lib/i18n";
import { QueryProvider } from "@/lib/query";
import { SentryClient } from "@/lib/sentry-client";
import "@fontsource/geist-mono/latin-400.css";
import "@fontsource/geist-mono/latin-500.css";
import "@fontsource/geist-sans/latin-400.css";
import "@fontsource/geist-sans/latin-500.css";
import "@fontsource/geist-sans/latin-600.css";
import "@fontsource/geist-sans/latin-700.css";
import "@fontsource/sora/latin-700.css";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Settlr",
  description: "Painel do operador — exceções, pagamentos, títulos e o agente de WhatsApp. Operator dashboard — exceptions, payments, invoices and the WhatsApp agent.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <head />
      <body>
        <SentryClient />
        <I18nProvider>
          <QueryProvider>{children}</QueryProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
