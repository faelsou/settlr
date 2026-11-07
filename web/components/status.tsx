import { clsx } from "@/lib/format";

const LABELS: Record<string, string> = {
  aberto: "Aberto",
  em_cobranca: "Em cobrança",
  promessa: "Promessa",
  em_negociacao: "Em negociação",
  renegociado: "Renegociado",
  parcialmente_pago: "Parcial",
  pago: "Pago",
  fila_humana: "Fila humana",
  sessao_canal: "Sessão caída",
  contestado: "Contestado",
  cancelado: "Cancelado",
  recebido_comprovante: "Comprovante",
  aguardando_banco: "Aguardando banco",
  recebido_banco: "Recebido banco",
  confirmado: "Confirmado",
  conciliado: "Conciliado",
  em_excecao: "Em exceção",
  descartado: "Descartado",
  aberta: "Aberta",
  resolvida: "Resolvida",
  rejeitada: "Rejeitada",
  pendente: "Pendente",
  aprovada: "Aprovada",
  agente: "Com o agente",
  aguardando_identidade: "Identidade",
  aguardando_comprovante: "Comprovante",
  aguardando_aprovacao: "Aprovação",
  humano: "Humano",
  encerrada: "Encerrada",
  pagamento_nao_identificado: "Não identificado",
  sugestao_match: "Sugestão de match",
  contestacao: "Contestação",
  leitura_baixa_confianca: "Leitura fraca",
  diferenca_valor: "Diferença de valor",
  comprovante: "Comprovante",
  extrato: "Extrato",
  webhook: "Webhook",
};

const TONES: Record<string, string> = {
  pago: "bg-signal-400 text-ink-950",
  conciliado: "bg-signal-400 text-ink-950",
  resolvida: "bg-signal-400 text-ink-950",
  aprovada: "bg-signal-400 text-ink-950",
  em_excecao: "bg-amber-100 text-amber-800",
  aberta: "bg-amber-100 text-amber-800",
  pendente: "bg-amber-100 text-amber-800",
  aguardando_banco: "bg-amber-100 text-amber-800",
  aguardando_aprovacao: "bg-amber-100 text-amber-800",
  contestado: "bg-red-100 text-red-800",
  contestacao: "bg-red-100 text-red-800",
  rejeitada: "bg-red-100 text-red-800",
  cancelado: "bg-red-100 text-red-800",
  descartado: "bg-red-100 text-red-800",
  fila_humana: "bg-red-100 text-red-800",
  sessao_canal: "bg-red-100 text-red-800",
  humano: "bg-sky-100 text-sky-800",
};

export function labelOf(value: string | null | undefined): string {
  if (!value) return "—";
  return LABELS[value] ?? value.replaceAll("_", " ");
}

export function Badge({ value }: { value: string | null | undefined }) {
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
