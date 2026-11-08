"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Button, Card, Field, FileButton, Input, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { documentBr, money, when } from "@/lib/format";
import type { Payment } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

const STATUSES = [
  { value: "", label: "Todos" },
  { value: "aguardando_banco", label: "Aguardando banco" },
  { value: "confirmado", label: "Confirmado" },
  { value: "conciliado", label: "Conciliado" },
  { value: "em_excecao", label: "Em exceção" },
];

const ORIGINS = [
  { value: "", label: "Todas as origens" },
  { value: "comprovante", label: "Comprovante" },
  { value: "extrato", label: "Extrato" },
  { value: "webhook", label: "Webhook" },
];

function isoLocal(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export default function PagamentosPage() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [origin, setOrigin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const today = isoLocal(new Date());
  const [start, setStart] = useState(() => isoLocal(new Date(new Date().getFullYear(), new Date().getMonth(), 1)));
  const [end, setEnd] = useState(today);
  const list = useQuery({
    queryKey: ["payments", status, origin],
    queryFn: () => api.payments({ status: status || undefined, origin: origin || undefined }),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "labels"],
    queryFn: () => api.invoices({}),
    staleTime: 15_000,
  });

  async function onImport(file: File) {
    setError(null);
    try {
      const result = await api.importStatement(file);
      toast(`Extrato importado: ${result.created} novos, ${result.duplicates} já existentes.`);
      list.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onExport() {
    setError(null);
    if (end < start) {
      setError("O fim do período é anterior ao início.");
      return;
    }
    setExporting(true);
    try {
      await api.exportSettlements(start, end);
      toast("Arquivo do contador baixado.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setExporting(false);
    }
  }

  async function openReceipt(id: string) {
    try {
      setReceipt(await api.receiptUrl(id));
    } catch (err) {
      setError(errorText(err));
    }
  }

  const columns: Column<Payment>[] = [
    { id: "amount", header: "Valor", cell: (payment) => <span className="font-semibold">{money(payment.amount)}</span> },
    {
      id: "payer",
      header: "Pagador",
      cell: (payment) => (
        <span>
          <span className="block">{payment.payer_name ?? "—"}</span>
          <span className="text-xs text-ink-700/60">{documentBr(payment.payer_doc)}</span>
        </span>
      ),
    },
    { id: "origin", header: "Origem", cell: (payment) => <Badge value={payment.origin} /> },
    { id: "status", header: "Status", cell: (payment) => <Badge value={payment.status} /> },
    { id: "bank", header: "Banco", cell: (payment) => (payment.bank_confirmed ? "Confirmado" : "Só comprovante") },
    { id: "when", header: "Quando", cell: (payment) => when(payment.paid_at) },
    {
      id: "receipt",
      header: "",
      cell: (payment) =>
        payment.has_receipt ? (
          <Button
            variant="ghost"
            onClick={(event) => {
              event.stopPropagation();
              openReceipt(payment.id);
            }}
          >
            Ver comprovante
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Conciliação"
        title="Pagamentos"
        hint="Comprovante sozinho nunca baixa. A baixa confirmada volta ao emissor, e o arquivo do período sai para o contador."
        actions={<FileButton label="Importar OFX/CSV" accept=".ofx,.csv,.txt" onFile={onImport} />}
      />

      <div className="flex flex-wrap items-end gap-3">
        <Segmented label="Status do pagamento" value={status} onChange={setStatus} options={STATUSES} />
        <Segmented label="Origem do pagamento" value={origin} onChange={setOrigin} options={ORIGINS} />
        <Field label="De">
          <Input
            type="date"
            aria-label="Início do período"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="w-40"
          />
        </Field>
        <Field label="Até">
          <Input
            type="date"
            aria-label="Fim do período"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="w-40"
          />
        </Field>
        <Button variant="outline" onClick={onExport} disabled={exporting}>
          {exporting ? "Gerando…" : "Arquivo do contador"}
        </Button>
      </div>

      {error ? <Banner>{error}</Banner> : null}

      <Card className="overflow-hidden">
        <DataTable
          rows={list.data?.items ?? []}
          columns={columns}
          rowKey={(payment) => payment.id}
          pending={list.isPending}
          error={list.isError ? errorText(list.error) : null}
          emptyTitle="Nenhum pagamento"
          emptyHint="Importe um extrato ou aguarde o webhook do banco."
          resetKey={`${status}:${origin}`}
          total={list.data?.total}
          renderExtra={(payment) =>
            payment.matches.length ? (
              <ul className="space-y-1 text-sm">
                {payment.matches.map((match) => {
                  const invoice = invoices.data?.items.find((item) => item.id === match.invoice_id);
                  return (
                    <li key={`${match.payment_id}-${match.invoice_id}`}>
                      {invoice?.external_id ?? "Título"} · {money(match.amount_applied)} · score {match.score}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-ink-700/70">Nenhum título vinculado.</p>
            )
          }
        />
      </Card>

      {receipt ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink-950/60 p-6" onClick={() => setReceipt(null)}>
          <img src={receipt} alt="Comprovante" className="max-h-full max-w-3xl rounded-2xl bg-white p-2" />
        </div>
      ) : null}
    </div>
  );
}
