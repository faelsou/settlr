"use client";

import { clsx } from "@/lib/format";
import { tr, useI18n } from "@/lib/i18n";
import { MESSAGES, type MessageKey } from "@/lib/messages";


const TONES: Record<string, string> = {
  pago: "bg-signal-400 text-ink-950",
  conciliado: "bg-signal-400 text-ink-950",
  resolvida: "bg-signal-400 text-ink-950",
  aprovada: "bg-signal-400 text-ink-950",
  em_excecao: "bg-amber-100 text-amber-800",
  aberta: "bg-amber-100 text-amber-800",
  pendente: "bg-amber-100 text-amber-800",
  aceito: "bg-sky-100 text-sky-800",
  enviado: "bg-sky-100 text-sky-800",
  sem_recibo: "bg-amber-100 text-amber-800",
  entregue: "bg-signal-400 text-ink-950",
  lido: "bg-signal-400 text-ink-950",
  recebido: "bg-signal-400 text-ink-950",
  falhou: "bg-red-100 text-red-800",
  nao_recebido: "bg-red-100 text-red-800",
  aguardando_banco: "bg-amber-100 text-amber-800",
  aguardando_aprovacao: "bg-amber-100 text-amber-800",
  contestado: "bg-red-100 text-red-800",
  contestacao: "bg-red-100 text-red-800",
  rejeitada: "bg-red-100 text-red-800",
  cancelado: "bg-red-100 text-red-800",
  descartado: "bg-red-100 text-red-800",
  leitura_baixa_confianca: "bg-amber-100 text-amber-800",
  transcricao_indisponivel: "bg-amber-100 text-amber-800",
  fila_humana: "bg-red-100 text-red-800",
  sessao_canal: "bg-red-100 text-red-800",
  humano: "bg-sky-100 text-sky-800",
};

export function deliveryCaption(
  delivery: string | null | undefined,
  file: string | null | undefined,
): string | null {
  const parts: string[] = [];
  if (delivery) parts.push(labelOf(delivery));
  if (file === "recebido") parts.push(tr("status.fileReceived"));
  if (file === "nao_recebido") parts.push(tr("status.fileNotReceived"));
  return parts.length ? parts.join(" · ") : null;
}

export function labelOf(value: string | null | undefined): string {
  if (!value) return "—";
  const key = `status.${value}`;
  return key in MESSAGES ? tr(key as MessageKey) : value.replaceAll("_", " ");
}

export function Badge({ value }: { value: string | null | undefined }) {
  useI18n(); // re-renderiza na troca de idioma
  if (!value) return <span>—</span>;
  return (
    <span
      className={clsx(
        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize",
        TONES[value] ?? "bg-paper-100 text-ink-800",
      )}
    >
      {labelOf(value)}
    </span>
  );
}
