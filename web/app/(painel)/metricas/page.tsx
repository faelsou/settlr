"use client";

import { MetricsBoard } from "@/components/metrics-board";
import { PageHeader } from "@/components/ui";

export default function MetricasPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Período"
        title="Métricas"
        hint="Recuperação, atraso contra a linha de base da implantação, promessas e o percentual de baixa automática. A linha mostra as últimas seis semanas."
      />
      <MetricsBoard periodControl />
    </div>
  );
}
