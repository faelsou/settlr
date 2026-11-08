"use client";

import { DataTable, type Column } from "@/components/data-table";
import { Badge } from "@/components/status";
import { Card, PageHeader, Segmented } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { when } from "@/lib/format";
import type { Delivery } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const FILTERS = [
  { value: "", label: "Todas" },
  { value: "falhou", label: "Falhas" },
];

function preview(body: string | null): string {
  if (!body || body === "[comprovante]") return "Comprovante";
  return body;
}

export default function EntregasPage() {
  const router = useRouter();
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
      header: "Devedor",
      cell: (row) => <span className="font-semibold">{row.debtor_name}</span>,
    },
    {
      id: "direction",
      header: "Direção",
      cell: (row) => (row.direction === "in" ? "Entrada" : "Saída"),
    },
    {
      id: "body",
      header: "Mensagem",
      className: "max-w-xs",
      cell: (row) => <span className="line-clamp-2">{preview(row.body)}</span>,
    },
    {
      id: "delivery",
      header: "Entrega",
      cell: (row) => <Badge value={row.delivery_status} />,
    },
    {
      id: "file",
      header: "Arquivo",
      cell: (row) => <Badge value={row.file_status} />,
    },
    { id: "when", header: "Quando", cell: (row) => when(row.created_at) },
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
            Título
          </Link>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="WhatsApp"
        title="Entregas"
        hint="Enviada, entregue, falha e se o arquivo foi guardado. O status é o do banco. Esta tela não consulta a Evolution."
        actions={<Segmented label="Entregas" value={filter} onChange={setFilter} options={FILTERS} />}
      />
      <Card className="overflow-hidden">
        <DataTable
          rows={list.data?.items ?? []}
          columns={columns}
          rowKey={(row) => row.id}
          pending={list.isPending}
          error={list.isError ? errorText(list.error) : null}
          emptyTitle={failed ? "Nenhuma falha" : "Nenhuma entrega"}
          emptyHint={
            failed
              ? "Quando uma saída falha, ela aparece aqui."
              : "A saída e o comprovante entram quando o banco já tem a linha."
          }
          onRow={(row) => router.push(`/conversas?id=${row.conversation_id}`)}
          resetKey={filter}
          total={list.data?.total}
        />
      </Card>
    </div>
  );
}
