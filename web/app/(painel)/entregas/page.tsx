"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { Card, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { when } from "@/lib/format";
import { tr, useI18n } from "@/lib/i18n";
import type { Delivery } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

function preview(body: string | null): string {
  if (!body || body === "[comprovante]") return tr("home.receipt");
  return body;
}

export default function EntregasPage() {
  const router = useRouter();
  const { t } = useI18n();
  const filters = [
    { value: "", label: t("inbox.all") },
    { value: "falhou", label: t("deliv.failures") },
  ];
  const [filter, setFilter] = useState("");
  const failed = filter === "falhou";
  const list = useQuery({
    queryKey: ["deliveries", failed ? "falhou" : "todas"],
    queryFn: () => api.deliveries(failed),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  });

  const columns: Column<Delivery>[] = [
    {
      id: "debtor",
      header: t("deliv.debtor"),
      cell: (row) => <span className="font-semibold">{row.debtor_name}</span>,
    },
    {
      id: "direction",
      header: t("deliv.direction"),
      cell: (row) => (row.direction === "in" ? t("deliv.in") : t("deliv.out")),
    },
    {
      id: "body",
      header: t("deliv.message"),
      className: "max-w-xs",
      cell: (row) => <span className="line-clamp-2">{preview(row.body)}</span>,
    },
    {
      id: "delivery",
      header: t("deliv.delivery"),
      cell: (row) => <Badge value={row.delivery_status} />,
    },
    {
      id: "file",
      header: t("deliv.file"),
      cell: (row) => <Badge value={row.file_status} />,
    },
    { id: "when", header: t("deliv.when"), cell: (row) => when(row.created_at) },
    {
      id: "invoice",
      header: "",
      cell: (row) =>
        row.invoice_id ? (
          <Link
            href={`/titulos/${row.invoice_id}`}
            className="font-semibold text-brand-700"
            onClick={(event) => event.stopPropagation()}
          >
            {t("deliv.invoice")}
          </Link>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="WhatsApp"
        title={t("nav.entregas")}
        hint={t("deliv.hint")}
        actions={<Segmented label={t("nav.entregas")} value={filter} onChange={setFilter} options={filters} />}
      />
      <Card className="overflow-hidden">
        <DataTable
          rows={list.data?.items ?? []}
          columns={columns}
          rowKey={(row) => row.id}
          pending={list.isPending}
          error={list.isError ? errorText(list.error) : null}
          emptyTitle={failed ? t("deliv.noFailures") : t("deliv.none")}
          emptyHint={
            failed
              ? t("deliv.noFailuresHint")
              : t("deliv.noneHint")
          }
          onRow={(row) => router.push(`/conversas?id=${row.conversation_id}`)}
          resetKey={filter}
          total={list.data?.total}
        />
      </Card>
    </div>
  );
}
