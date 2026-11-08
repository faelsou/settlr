"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Card, FileButton, Input, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money } from "@/lib/format";
import { useDebouncedValue } from "@/lib/hooks";
import type { Invoice } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const STATUSES = [
  { value: "", label: "Todos" },
  { value: "aberto", label: "Aberto" },
  { value: "em_cobranca", label: "Em cobrança" },
  { value: "promessa", label: "Promessa" },
  { value: "em_negociacao", label: "Negociação" },
  { value: "parcialmente_pago", label: "Parcial" },
  { value: "pago", label: "Pago" },
  { value: "fila_humana", label: "Fila humana" },
  { value: "contestado", label: "Contestado" },
];

const columns: Column<Invoice>[] = [
  {
    id: "debtor",
    header: "Devedor",
    cell: (invoice) => (
      <span>
        <Link href={`/titulos/${invoice.id}`} className="font-semibold hover:underline" onClick={(event) => event.stopPropagation()}>
          {invoice.debtor.name}
        </Link>
        <span className="mt-0.5 block text-xs text-ink-700/60">{documentBr(invoice.debtor.document)}</span>
      </span>
    ),
  },
  { id: "ref", header: "Referência", cell: (invoice) => invoice.external_id },
  { id: "amount", header: "Valor", cell: (invoice) => money(invoice.amount) },
  { id: "due", header: "Vencimento", cell: (invoice) => day(invoice.due_date) },
  { id: "status", header: "Status", cell: (invoice) => <Badge value={invoice.status} /> },
];

export function TitulosScreen() {
  const params = useSearchParams();
  const toast = useToast();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const query = useDebouncedValue(q, 300);
  const list = useQuery({
    queryKey: ["invoices", status, query],
    queryFn: () => api.invoices({ status: status || undefined, q: query || undefined }),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });
  const semPagamento = useQuery({
    queryKey: ["invoices", "sem-pagamento", query],
    queryFn: () => api.invoices({ semPagamento: true, q: query || undefined }),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    setQ(params.get("q") ?? "");
  }, [params]);

  async function onImport(file: File) {
    setError(null);
    try {
      const result = await api.importInvoices(file);
      toast(`Importação: ${result.created} criados, ${result.updated} atualizados.`);
      list.refetch();
      semPagamento.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Carteira"
        title="Títulos"
        hint="Centro do modelo: régua, conversas e pagamentos apontam para o título."
        actions={<FileButton label="Importar CSV" accept=".csv" onFile={onImport} />}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Buscar por nome, documento ou referência"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          className="max-w-md"
        />
        <Segmented label="Status do título" value={status} onChange={setStatus} options={STATUSES} />
      </div>

      {error ? <Banner>{error}</Banner> : null}

      {semPagamento.data && semPagamento.data.total > 0 ? (
        <Card className="overflow-hidden">
          <div className="border-b border-paper-200 px-6 py-4">
            <h2 className="font-display text-xl">Sem PIX ou boleto</h2>
            <p className="mt-1 max-w-2xl text-sm text-ink-700/70">
              Estes títulos não entram na régua. Quando o código chegar, sai só a etapa do dia, sem as
              anteriores. Confira esta lista antes de ativar a conta.
            </p>
          </div>
          <DataTable
            rows={semPagamento.data.items}
            columns={columns}
            rowKey={(invoice) => invoice.id}
            pending={semPagamento.isPending}
            error={semPagamento.isError ? errorText(semPagamento.error) : null}
            emptyTitle="Nenhum título sem código"
            resetKey={`sem:${query}`}
            total={semPagamento.data.total}
          />
        </Card>
      ) : null}

      <Card className="overflow-hidden">
        <DataTable
          rows={list.data?.items ?? []}
          columns={columns}
          rowKey={(invoice) => invoice.id}
          pending={list.isPending}
          error={list.isError ? errorText(list.error) : null}
          emptyTitle="Nenhum título"
          emptyHint="Importe a planilha do emissor ou cadastre via webhook."
          resetKey={`${status}:${query}`}
          total={list.data?.total}
        />
      </Card>
    </div>
  );
}
