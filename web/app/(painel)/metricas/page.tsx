"use client";

import { MetricsBoard } from "@/components/metrics-board";
import { PageHeader } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

export default function MetricasPage() {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("metrics.period")}
        title={t("nav.metricas")}
        hint={t("met.hint")}
      />
      <MetricsBoard periodControl />
    </div>
  );
}
