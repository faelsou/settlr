"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge, labelOf } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Button, Card, Dialog, Empty, Field, Input, PageHeader, Segmented, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { canSettle } from "@/lib/roles";
import { tr, useI18n } from "@/lib/i18n";
import { day, documentBr, money, when } from "@/lib/format";
import type { Invoice, ReviewException, Suggestion } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

const PAYMENT_TYPES = new Set([
  "sugestao_match",
  "pagamento_nao_identificado",
  "diferenca_valor",
]);

type Allocation = { invoice_id: string; amount: string };

export default function ExcecoesPage() {
  const client = useQueryClient();
  const { t } = useI18n();
  const [status, setStatus] = useState("aberta");
  const list = useQuery({
    queryKey: ["exceptions", status],
    queryFn: () => api.exceptions(status),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });
  const [selected, setSelected] = useState<ReviewException | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("exc.eyebrow")}
        title={t("nav.excecoes")}
        hint={t("exc.hint")}
        actions={
          <Segmented
            label={t("exc.statusLabel")}
            value={status}
            onChange={setStatus}
            options={[
              { value: "aberta", label: t("exc.open") },
              { value: "resolvida", label: t("exc.resolved") },
              { value: "rejeitada", label: t("exc.rejected") },
            ]}
          />
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="overflow-hidden">
          <DataTable
            rows={list.data?.items ?? []}
            columns={exceptionColumns()}
            rowKey={(item) => item.id}
            pending={list.isPending}
            error={list.isError ? errorText(list.error) : null}
            emptyTitle={t("exc.empty")}
            emptyHint={t("exc.emptyHint")}
            onRow={setSelected}
            activeKey={selected?.id}
            resetKey={status}
            total={list.data?.total}
          />
        </Card>

        {selected ? (
          <ExceptionDetail
            key={selected.id}
            item={selected}
            onDone={() => {
              setSelected(null);
              client.invalidateQueries({ queryKey: ["exceptions"] });
            }}
          />
        ) : (
          <Card>
            <Empty title={t("exc.select")} hint={t("exc.selectHint")} />
          </Card>
        )}
      </div>
    </div>
  );
}

function ExceptionDetail({ item, onDone }: { item: ReviewException; onDone: () => void }) {
  const toast = useToast();
  const { t } = useI18n();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const settles = canSettle(me.data?.role);
  const suggestions = item.details.suggestions ?? [];
  const [note, setNote] = useState("");
  const [ask, setAsk] = useState<"confirm" | "reject" | null>(null);
  const [contestation, setContestation] = useState<"cobranca" | "devedor">("cobranca");
  const [allocations, setAllocations] = useState<Allocation[]>(
    suggestions[0]?.allocations.map((a) => ({ invoice_id: a.invoice_id, amount: a.amount })) ?? [],
  );
  const [query, setQuery] = useState("");
  const [receipt, setReceipt] = useState(() => receiptDraft(item));
  const catalog = useQuery({
    queryKey: ["invoices", "labels"],
    queryFn: () => api.invoices({}),
    staleTime: 15_000,
  });
  const invoices = useQuery({
    queryKey: ["invoice-search", query],
    queryFn: () => api.invoices({ q: query }),
    enabled: query.length >= 2,
  });

  const confirm = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { note };
      if (PAYMENT_TYPES.has(item.type)) body.allocations = allocations.map((a) => ({ ...a, amount: Number(a.amount) }));
      if (item.type === "leitura_baixa_confianca") {
        body.receipt = { ...receipt, amount: Number(receipt.amount), paid_at: new Date(receipt.paid_at).toISOString() };
      }
      if (item.type === "contestacao") body.contestation = contestation;
      return api.confirmException(item.id, body);
    },
    onSuccess: () => {
      toast(t("exc.confirmed"));
      setAsk(null);
      onDone();
    },
    onError: () => setAsk(null),
  });
  const reject = useMutation({
    mutationFn: () => api.rejectException(item.id, { note, discard_payment: false }),
    onSuccess: () => {
      toast(t("exc.rejectedToast"));
      setAsk(null);
      onDone();
    },
    onError: () => setAsk(null),
  });

  const invoiceMap = useMemo(() => {
    const map = new Map<string, Invoice>();
    catalog.data?.items.forEach((inv) => map.set(inv.id, inv));
    invoices.data?.items.forEach((inv) => map.set(inv.id, inv));
    return map;
  }, [catalog.data, invoices.data]);
  // A contestação vale só para o título citado na conversa (item.invoice_id).
  const contested = catalog.data?.items.filter(
    (inv) => inv.status === "contestado" && inv.id === item.invoice_id,
  ) ?? [];

  return (
    <Card className="p-6">
      <p className="text-xs font-mono uppercase tracking-[0.04em] text-ink-700">{labelOf(item.type)}</p>
      <h2 className="mt-1 font-display text-2xl">{t("exc.review")}</h2>
      <ExceptionSummary item={item} />

      {item.payment ? (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-ink-700/60">{t("inv.amount")}</dt>
            <dd className="font-semibold">{money(item.payment.amount)}</dd>
          </div>
          <div>
            <dt className="text-ink-700/60">{t("exc.paidAt")}</dt>
            <dd>{when(item.payment.paid_at)}</dd>
          </div>
          <div>
            <dt className="text-ink-700/60">{t("pay.payer")}</dt>
            <dd>{item.payment.payer_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-ink-700/60">{t("exc.document")}</dt>
            <dd>{documentBr(item.payment.payer_doc)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-ink-700/60">{t("exc.bankE2e")}</dt>
            <dd>
              {item.payment.payer_bank ?? "—"} · {item.payment.e2e_id ?? t("exc.noE2e")}
              {item.payment.bank_confirmed ? "" : t("exc.awaitingBank")}
            </dd>
          </div>
        </dl>
      ) : null}

      {suggestions.length > 0 ? (
        <div className="mt-5 space-y-2">
          <p className="text-xs font-mono font-medium uppercase tracking-[0.04em] text-ink-700/60">{t("exc.suggestions")}</p>
          {suggestions.map((s, idx) => (
            <button
              key={`${s.method}-${idx}`}
              type="button"
              onClick={() => setAllocations(s.allocations.map((a) => ({ invoice_id: a.invoice_id, amount: a.amount })))}
              className="w-full rounded-xl border border-paper-200 px-3 py-2 text-left text-sm hover:border-brand-600"
            >
              <span className="font-semibold">{labelOf(s.method)}</span>
              <span className="ml-2 text-ink-700/60">{t("exc.score", { score: s.score })}</span>
              <SuggestionLines suggestion={s} invoices={invoiceMap} />
            </button>
          ))}
        </div>
      ) : null}

      {PAYMENT_TYPES.has(item.type) ? (
        <div className="mt-5 space-y-3">
          <Field label={t("exc.searchInvoice")}>
            <Input placeholder={t("exc.searchPh")} value={query} onChange={(e) => setQuery(e.target.value)} />
          </Field>
          {invoices.data?.items.slice(0, 5).map((inv) => (
            <button
              key={inv.id}
              type="button"
              onClick={() =>
                setAllocations((prev) =>
                  prev.some((a) => a.invoice_id === inv.id)
                    ? prev
                    : [...prev, { invoice_id: inv.id, amount: String(Number(inv.amount) - Number(inv.amount_paid)) }],
                )
              }
              className="flex w-full justify-between rounded-xl bg-paper-50 px-3 py-2 text-left text-sm"
            >
              <span>
                {inv.debtor.name} · {inv.external_id}
              </span>
              <span>{money(inv.amount)}</span>
            </button>
          ))}
          {allocations.map((alloc, idx) => (
            <div key={alloc.invoice_id} className="grid grid-cols-[1fr_120px_auto] items-center gap-2">
              <p className="truncate text-sm">{invoiceLabel(invoiceMap.get(alloc.invoice_id)) ?? alloc.invoice_id}</p>
              <Input
                value={alloc.amount}
                onChange={(e) =>
                  setAllocations((prev) => prev.map((a, i) => (i === idx ? { ...a, amount: e.target.value } : a)))
                }
              />
              <Button variant="ghost" type="button" onClick={() => setAllocations((prev) => prev.filter((_, i) => i !== idx))}>
                {t("exc.remove")}
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {item.type === "transcricao_indisponivel" && item.details.file_key ? (
        <div className="mt-5">
          <ReceiptPreview exceptionId={item.id} contentType={item.details.content_type} />
        </div>
      ) : null}

      {item.type === "leitura_baixa_confianca" ? (
        <div className="mt-5 grid gap-3">
          {item.details.file_key ? <ReceiptPreview exceptionId={item.id} contentType={item.details.content_type} /> : null}
          <Field label={t("inv.amount")}>
            <Input value={receipt.amount} onChange={(e) => setReceipt({ ...receipt, amount: e.target.value })} />
          </Field>
          <Field label={t("exc.paidAt")}>
            <Input type="datetime-local" value={receipt.paid_at} onChange={(e) => setReceipt({ ...receipt, paid_at: e.target.value })} />
          </Field>
          <Field label="E2E">
            <Input value={receipt.e2e_id} onChange={(e) => setReceipt({ ...receipt, e2e_id: e.target.value })} />
          </Field>
          <Field label={t("pay.payer")}>
            <Input value={receipt.payer_name} onChange={(e) => setReceipt({ ...receipt, payer_name: e.target.value })} />
          </Field>
          <Field label={t("exc.payerDoc")}>
            <Input value={receipt.payer_doc} onChange={(e) => setReceipt({ ...receipt, payer_doc: e.target.value })} />
          </Field>
        </div>
      ) : null}

      {item.type === "contestacao" && contested.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm">
          {contested.map((inv) => (
            <li key={inv.id}>
              {inv.debtor.name} · {inv.external_id} · {money(inv.amount)}
            </li>
          ))}
        </ul>
      ) : null}

      {item.type === "contestacao" ? (
        <Field label={t("exc.favor")}>
          <Segmented
            label={t("exc.favor")}
            value={contestation}
            onChange={setContestation}
            options={[
              { value: "cobranca", label: t("exc.favorCharge") },
              { value: "devedor", label: t("exc.favorDebtor") },
            ]}
          />
        </Field>
      ) : null}

      <Field label={t("exc.note")}>
        <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>

      {confirm.isError ? <Banner>{errorText(confirm.error)}</Banner> : null}
      {reject.isError ? <Banner>{errorText(reject.error)}</Banner> : null}

      {item.status === "aberta" ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {item.type === "contestacao" && me.data && !settles ? (
            <p className="w-full text-sm text-ink-700/70">{t("exc.financeDisputes")}</p>
          ) : PAYMENT_TYPES.has(item.type) && me.data && !settles ? (
            <p className="w-full text-sm text-ink-700/70">{t("exc.financeSettles")}</p>
          ) : (
            <Button onClick={() => setAsk("confirm")} disabled={confirm.isPending}>
              {t("exc.confirm")}
            </Button>
          )}
          {item.type === "contestacao" && me.data && !settles ? null : (
            <Button variant="outline" onClick={() => setAsk("reject")} disabled={reject.isPending}>
              {t("exc.reject")}
            </Button>
          )}
        </div>
      ) : (
        <p className="mt-4 text-sm text-ink-700/70">
          {t("exc.handled", { date: day(item.resolved_at), who: item.assignee ?? "—" })}
        </p>
      )}
      <Dialog
        open={ask != null}
        title={ask === "reject" ? t("exc.askReject") : t("exc.askConfirm")}
        body={
          item.type === "transcricao_indisponivel"
            ? t("exc.bodyAudio")
            : ask === "reject"
              ? t("exc.bodyReject")
              : t("exc.bodyConfirm")
        }
        confirmLabel={ask === "reject" ? t("exc.reject") : t("exc.confirm")}
        danger={ask === "reject"}
        busy={confirm.isPending || reject.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => {
          if (ask === "reject") reject.mutate();
          else confirm.mutate();
        }}
      />
    </Card>
  );
}

/* Chamada dentro de ExcecoesPage, que já usa useI18n(): tr() pega o idioma corrente. */
const exceptionColumns = (): Column<ReviewException>[] => [
  { id: "type", header: tr("exc.type"), cell: (item) => <Badge value={item.type} /> },
  { id: "payment", header: tr("exc.payment"), cell: (item) => paymentLabel(item) },
  { id: "when", header: tr("deliv.when"), cell: (item) => when(item.created_at) },
  { id: "status", header: tr("inv.status"), cell: (item) => <Badge value={item.status} /> },
];

function paymentLabel(item: ReviewException): string {
  if (item.payment) return `${money(item.payment.amount)} · ${item.payment.payer_name ?? tr("home.noName")}`;
  const extracted = item.details.extraction;
  if (extracted?.amount != null) return `${money(extracted.amount)} · ${extracted.payer_name || tr("home.noName")}`;
  return "—";
}

function receiptDraft(item: ReviewException) {
  const extracted = item.details.extraction;
  const paidAt = extracted?.paid_at ?? item.payment?.paid_at ?? "";
  return {
    amount: extracted?.amount != null ? String(extracted.amount) : (item.payment?.amount ?? ""),
    paid_at: paidAt ? paidAt.slice(0, 16) : "",
    e2e_id: extracted?.e2e_id ?? item.payment?.e2e_id ?? "",
    payer_doc: extracted?.payer_doc ?? item.payment?.payer_doc ?? "",
    payer_name: extracted?.payer_name ?? item.payment?.payer_name ?? "",
  };
}

function ExceptionSummary({ item }: { item: ReviewException }) {
  const { t } = useI18n();
  const problems = item.details.problems ?? [];
  const reason = item.details.reason ?? item.details.motivo;
  if (!reason && problems.length === 0) {
    return <p className="mt-2 text-sm text-ink-700/70">{t("exc.noDetail")}</p>;
  }
  return (
    <div className="mt-2 space-y-1 text-sm text-ink-700/80">
      {reason ? <p>{reason}</p> : null}
      {problems.map((problem) => (
        <p key={problem}>{problem}</p>
      ))}
    </div>
  );
}

function ReceiptPreview({ exceptionId, contentType }: { exceptionId: string; contentType?: string }) {
  const { t } = useI18n();
  const [url, setUrl] = useState<string | null>(null);
  const [kind, setKind] = useState(contentType ?? "");

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    api
      .exceptionFile(exceptionId)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
        setKind(blob.type || contentType || "");
      })
      .catch(() => {
        if (active) setUrl(null);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [exceptionId, contentType]);

  if (!url) return null;
  if (kind.startsWith("audio/")) {
    return <audio controls src={url} className="w-full" />;
  }
  if (kind.startsWith("image/")) {
    return <img src={url} alt={t("exc.receiptSent")} className="max-h-72 w-full rounded-xl object-contain bg-paper-50" />;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-brand-700 underline">
      {t("exc.openReceipt")}
    </a>
  );
}

function invoiceLabel(invoice: Invoice | undefined): string | null {
  if (!invoice) return null;
  return `${invoice.debtor.name} · ${invoice.external_id}`;
}

function SuggestionLines({ suggestion, invoices }: { suggestion: Suggestion; invoices: Map<string, Invoice> }) {
  const { t } = useI18n();
  return (
    <p className="mt-1 text-ink-700/70">
      {suggestion.allocations
        .map((a) => `${invoiceLabel(invoices.get(a.invoice_id)) ?? t("appr.invoice")} · ${money(a.amount)}`)
        .join(" · ")}
    </p>
  );
}
