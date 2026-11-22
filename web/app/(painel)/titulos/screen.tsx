"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Card, FileButton, Input, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money } from "@/lib/format";
import { useDebouncedValue } from "@/lib/hooks";
import { useI18n, type Vars } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import type { Invoice } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

const STATUSES: { value: string; label: MessageKey }[] = [
  { value: "", label: "inv.all" },
  { value: "aberto", label: "status.aberto" },
  { value: "em_cobranca", label: "status.em_cobranca" },
  { value: "promessa", label: "status.promessa" },
  { value: "em_negociacao", label: "inv.negotiation" },
  { value: "parcialmente_pago", label: "status.parcialmente_pago" },
  { value: "pago", label: "status.pago" },
  { value: "fila_humana", label: "status.fila_humana" },
  { value: "contestado", label: "status.contestado" },
];

const invoiceColumns = (t: (key: MessageKey, vars?: Vars) => string): Column<Invoice>[] => [
  {
    id: "debtor",
    header: t("inv.debtor"),
    cell: (invoice) => (
      <span>
        <Link href={`/titulos/${invoice.id}`} className="font-semibold hover:underline" onClick={(event) => event.stopPropagation()}>
          {invoice.debtor.name}
        </Link>
        <span className="mt-0.5 block text-xs text-ink-700/60">{documentBr(invoice.debtor.document)}</span>
      </span>
    ),
  },
  { id: "ref", header: t("inv.reference"), cell: (invoice) => invoice.external_id },
  { id: "amount", header: t("inv.amount"), cell: (invoice) => money(invoice.amount) },
  { id: "due", header: t("inv.due"), cell: (invoice) => day(invoice.due_date) },
  { id: "status", header: t("inv.status"), cell: (invoice) => <Badge value={invoice.status} /> },
];

export function TitulosScreen() {
  const params = useSearchParams();
  const toast = useToast();
  const { t } = useI18n();
  const columns = invoiceColumns(t);
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
      toast(t("inv.imported", { created: result.created, updated: result.updated }));
      list.refetch();
      semPagamento.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("inv.eyebrow")}
        title={t("nav.titulos")}
        hint={t("inv.hint")}
        actions={<FileButton label={t("inv.import")} accept=".csv" onFile={onImport} />}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder={t("inv.searchPh")}
          value={q}
          onChange={(event) => setQ(event.target.value)}
          className="max-w-md"
        />
        <Segmented
          label={t("inv.statusLabel")}
          value={status}
          onChange={setStatus}
          options={STATUSES.map((item) => ({ value: item.value, label: t(item.label) }))}
        />
      </div>

      {error ? <Banner>{error}</Banner> : null}

      {semPagamento.data && semPagamento.data.total > 0 ? (
        <Card className="overflow-hidden">
          <div className="border-b border-paper-200 px-6 py-4">
            <h2 className="font-display text-xl">{t("inv.noCode")}</h2>
            <p className="mt-1 max-w-2xl text-sm text-ink-700/70">
              {t("inv.noCodeHint")}
            </p>
          </div>
          <DataTable
            rows={semPagamento.data.items}
            columns={columns}
            rowKey={(invoice) => invoice.id}
            pending={semPagamento.isPending}
            error={semPagamento.isError ? errorText(semPagamento.error) : null}
            emptyTitle={t("inv.noCodeEmpty")}
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
          emptyTitle={t("inv.empty")}
          emptyHint={t("inv.emptyHint")}
          resetKey={`${status}:${query}`}
          total={list.data?.total}
        />
      </Card>
    </div>
  );
}
