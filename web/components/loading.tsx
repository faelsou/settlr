"use client";

import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";

/** Texto de espera para páginas de servidor (fallback do Suspense), que não usam hooks. */
export function LoadingText({ text, className = "text-sm text-ink-700/70" }: { text: MessageKey; className?: string }) {
  const { t } = useI18n();
  return <p className={className}>{t(text)}</p>;
}
