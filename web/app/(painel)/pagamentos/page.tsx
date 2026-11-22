"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Button, Card, Field, FileButton, Input, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { documentBr, money, when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import type { Payment } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

const STATUSES: { value: string; label: MessageKey }[] = [
  { value: "", label: "inv.all" },
  { value: "aguardando_banco", label: "status.aguardando_banco" },
  { value: "confirmado", label: "status.confirmado" },
  { value: "conciliado", label: "status.conciliado" },
  { value: "em_excecao", label: "status.em_excecao" },
];

const ORIGINS: { value: string; label: MessageKey }[] = [
  { value: "", label: "pay.allOrigins" },
  { value: "comprovante", label: "status.comprovante" },
  { value: "extrato", label: "status.extrato" },
  { value: "webhook", label: "status.webhook" },
];

function isoLocal(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export default function PagamentosPage() {
  const toast = useToast();
  const { t } = useI18n();
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
      toast(t("pay.imported", { created: result.created, duplicates: result.duplicates }));
      list.refetch();
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function onExport() {
    setError(null);
    if (end < start) {
      setError(t("pay.badRange"));
      return;
    }
    setExporting(true);
    try {
      await api.exportSettlements(start, end);
      toast(t("pay.exported"));
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
    { id: "amount", header: t("inv.amount"), cell: (payment) => <span className="font-semibold">{money(payment.amount)}</span> },
    {
      id: "payer",
      header: t("pay.payer"),
      cell: (payment) => (
        <span>
          <span className="block">{payment.payer_name ?? "—"}</span>
          <span className="text-xs text-ink-700/60">{documentBr(payment.payer_doc)}</span>
        </span>
      ),
    },
    { id: "origin", header: t("pay.origin"), cell: (payment) => <Badge value={payment.origin} /> },
    { id: "status", header: t("inv.status"), cell: (payment) => <Badge value={payment.status} /> },
    { id: "bank", header: t("pay.bank"), cell: (payment) => (payment.bank_confirmed ? t("pay.bankOk") : t("pay.onlyReceipt")) },
    { id: "when", header: t("deliv.when"), cell: (payment) => when(payment.paid_at) },
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
            {t("pay.viewReceipt")}
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("pay.eyebrow")}
        title={t("nav.pagamentos")}
        hint={t("pay.hint")}
      />

      <Card className="flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <h2 className="font-semibold">{t("pay.sheetTitle")}</h2>
          <p className="mt-1 max-w-xl text-sm text-ink-700/70">
            {t("pay.sheetHint")}
          </p>
        </div>
        <FileButton label={t("pay.importSheet")} accept=".ofx,.csv,.txt" onFile={onImport} />
      </Card>

      <div className="flex flex-wrap items-end gap-3">
        <Segmented
          label={t("pay.statusLabel")}
          value={status}
          onChange={setStatus}
          options={STATUSES.map((item) => ({ value: item.value, label: t(item.label) }))}
        />
        <Segmented
          label={t("pay.originLabel")}
          value={origin}
          onChange={setOrigin}
          options={ORIGINS.map((item) => ({ value: item.value, label: t(item.label) }))}
        />
        <Field label={t("pay.from")}>
          <Input
            type="date"
            aria-label={t("pay.startAria")}
            value={start}
            onChange={(event) => setStart(event.target.value)}
            className="w-40"
          />
        </Field>
        <Field label={t("pay.to")}>
          <Input
            type="date"
            aria-label={t("pay.endAria")}
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            className="w-40"
          />
        </Field>
        <Button variant="outline" onClick={onExport} disabled={exporting}>
          {exporting ? t("pay.generating") : t("pay.accountant")}
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
          emptyTitle={t("pay.empty")}
          emptyHint={t("pay.emptyHint")}
          resetKey={`${status}:${origin}`}
          total={list.data?.total}
          renderExtra={(payment) =>
            payment.matches.length ? (
              <ul className="space-y-1 text-sm">
                {payment.matches.map((match) => {
                  const invoice = invoices.data?.items.find((item) => item.id === match.invoice_id);
                  return (
                    <li key={`${match.payment_id}-${match.invoice_id}`}>
                      {t("pay.match", { ref: invoice?.external_id ?? t("deliv.invoice"), amount: money(match.amount_applied), score: match.score })}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-ink-700/70">{t("pay.noLink")}</p>
            )
          }
        />
      </Card>

      {receipt ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink-950/60 p-6" onClick={() => setReceipt(null)}>
          <img src={receipt} alt={t("home.receipt")} className="max-h-full max-w-3xl rounded-2xl bg-white p-2" />
        </div>
      ) : null}
    </div>
  );
}
