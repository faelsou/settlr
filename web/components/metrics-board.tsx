"use client";

import { Sparkline, Ticker } from "@/components/visuals";
import { Banner, Card, Segmented, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { currentLang, tr, useI18n } from "@/lib/i18n";
import { MESSAGES, type MessageKey } from "@/lib/messages";
import type { ReguaVariantMetrics } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

const PERIODS = ["7", "30", "90"] as const;

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function rangeFor(days: number): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { start: isoDate(start), end: isoDate(end) };
}

function lastWeeks(count = 6): { start: string; end: string }[] {
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  return Array.from({ length: count }, (_, index) => {
    const offset = count - 1 - index;
    const weekEnd = new Date(end);
    weekEnd.setUTCDate(weekEnd.getUTCDate() - offset * 7);
    const weekStart = new Date(weekEnd);
    weekStart.setUTCDate(weekStart.getUTCDate() - 6);
    return { start: isoDate(weekStart), end: isoDate(weekEnd) };
  });
}

function weekLabel(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat(currentLang(), { day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(Date.UTC(year, month - 1, day));
}

function lateHint(current: number | null, baseline: number | null): string {
  if (baseline == null) return tr("metrics.afterDue");
  const base = num(baseline);
  if (current == null) return tr("metrics.baseline", { base });
  const diff = current - baseline;
  const gap = num(Math.abs(diff));
  if (diff < -0.05) return tr("metrics.belowBase", { gap, base });
  if (diff > 0.05) return tr("metrics.aboveBase", { gap, base });
  return tr("metrics.atBase", { base });
}

function deltaText(current: number | null | undefined, previous: number | null | undefined): string | null {
  if (current == null || previous == null) return null;
  const points = num(Math.abs((current - previous) * 100));
  if (current - previous > 0.0001) return tr("metrics.up", { points });
  if (previous - current > 0.0001) return tr("metrics.down", { points });
  return tr("metrics.flat");
}

export function MetricsBoard({ periodControl = false }: { periodControl?: boolean }) {
  const { t } = useI18n();
  const [days, setDays] = useState<(typeof PERIODS)[number]>("30");
  const range = useMemo(() => rangeFor(Number(days)), [days]);
  const weeks = useMemo(() => lastWeeks(6), []);
  const metrics = useQuery({
    queryKey: ["metrics", range.start, range.end],
    queryFn: () => api.metrics(range.start, range.end),
  });
  const series = useQuery({
    queryKey: ["metrics-series", weeks],
    queryFn: () => Promise.all(weeks.map((week) => api.metrics(week.start, week.end))),
    staleTime: 60_000,
  });

  const data = metrics.data;
  const points = series.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-700/70">
          {data ? t("metrics.periodRange", { start: data.period_start, end: data.period_end }) : t("metrics.last30")}
        </p>
        {periodControl ? (
          <Segmented
            label={t("metrics.period")}
            value={days}
            onChange={setDays}
            options={PERIODS.map((value) => ({ value, label: t("metrics.days", { n: value }) }))}
          />
        ) : null}
      </div>
      {metrics.isError ? <Banner>{errorText(metrics.error)}</Banner> : null}
      {!data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-36" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <TrendCard
            className="md:col-span-2"
            title={t("metrics.recovery")}
            value={data.recovery_rate}
            format={pct}
            hint={t("metrics.recoveryHint", { recovered: money(data.recovered_amount), overdue: money(data.overdue_amount) })}
            series={points?.map((point) => point.recovery_rate) ?? null}
            labels={points ? [weekLabel(points[0].period_start), weekLabel(points[points.length - 1].period_end)] : undefined}
            delta={deltaText(points?.at(-1)?.recovery_rate, points?.at(-2)?.recovery_rate)}
            seriesPending={series.isPending}
          />
          <TrendCard
            className="md:col-span-2"
            title={t("metrics.auto")}
            value={data.auto_reconciliation_rate}
            format={pct}
            hint={t("metrics.autoHint", { auto: data.auto_reconciled, total: data.payments_reconciled })}
            series={points?.map((point) => point.auto_reconciliation_rate) ?? null}
            labels={points ? [weekLabel(points[0].period_start), weekLabel(points[points.length - 1].period_end)] : undefined}
            delta={deltaText(points?.at(-1)?.auto_reconciliation_rate, points?.at(-2)?.auto_reconciliation_rate)}
            seriesPending={series.isPending}
          />
          <Stat
            title={t("metrics.daysLate")}
            value={data.avg_days_late}
            format={(value) => num(value)}
            hint={lateHint(data.avg_days_late, data.baseline_avg_days_late)}
          />
          <Stat
            title={t("metrics.promises")}
            value={data.promise_kept_rate}
            format={pct}
            hint={t("metrics.ofTotal", { a: data.promises_kept, b: data.promises_made })}
          />
          <Stat
            title={t("metrics.openExc")}
            value={data.exceptions_open}
            format={(value) => String(Math.round(value))}
            hint={t("metrics.openExcHint")}
          />
          <Stat
            title={t("metrics.resolution")}
            value={data.avg_exception_resolution_hours}
            format={(value) => `${num(value)} h`}
            hint={t("metrics.resolutionHint")}
          />
        </div>
      )}
      {data?.regua_variants?.length ? <VariantComparison variants={data.regua_variants} /> : null}
    </div>
  );
}

function TrendCard({
  className,
  title,
  value,
  format,
  hint,
  series,
  labels,
  delta,
  seriesPending,
}: {
  className?: string;
  title: string;
  value: number | null;
  format: (value: number) => string;
  hint: string;
  series: Array<number | null> | null;
  labels?: [string, string];
  delta: string | null;
  seriesPending: boolean;
}) {
  return (
    <Card className={`p-5 ${className ?? ""}`}>
      <p className="text-xs font-mono uppercase tracking-[0.04em] text-ink-700/60">{title}</p>
      <p className="mt-2 font-display text-4xl tracking-tight">{value == null ? "—" : <Ticker value={value} format={format} />}</p>
      <p className="mt-2 text-sm text-ink-700/70">{hint}</p>
      {seriesPending ? <Skeleton className="mt-4 h-16" /> : null}
      {series ? <Sparkline values={series} startLabel={labels?.[0]} endLabel={labels?.[1]} /> : null}
      {delta ? <p className="mt-2 text-xs text-ink-700/60">{delta}</p> : null}
    </Card>
  );
}

function Stat({
  title,
  value,
  format,
  hint,
}: {
  title: string;
  value: number | null;
  format: (value: number) => string;
  hint: string;
}) {
  return (
    <Card className="p-5">
      <p className="text-xs font-mono uppercase tracking-[0.04em] text-ink-700/60">{title}</p>
      <p className="mt-2 font-display text-3xl tracking-tight">{value == null ? "—" : <Ticker value={value} format={format} />}</p>
      <p className="mt-2 text-sm text-ink-700/70">{hint}</p>
    </Card>
  );
}

function variantLabel(variant: string): string {
  const key = `variant.${variant}`;
  return key in MESSAGES ? tr(key as MessageKey) : variant;
}

function VariantComparison({ variants }: { variants: ReguaVariantMetrics[] }) {
  const { t } = useI18n();
  return (
    <Card className="p-5">
      <p className="text-xs font-mono uppercase tracking-[0.04em] text-ink-700/60">{t("variant.title")}</p>
      <p className="mt-1 text-sm text-ink-700/70">
        {t("variant.hint")}
      </p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {variants.map((item) => (
          <div key={item.variant} className="rounded-2xl border border-ink-700/10 p-4">
            <p className="text-sm font-semibold">{variantLabel(item.variant)}</p>
            <p className="mt-2 font-display text-3xl tracking-tight">{pct(item.recovery_rate)}</p>
            <p className="mt-1 text-sm text-ink-700/70">
              {t("variant.recovered", { recovered: money(item.recovered_amount), overdue: money(item.overdue_amount), n: item.invoices })}
            </p>
            <p className="mt-1 text-sm text-ink-700/70">
              {t("variant.dispatches", { n: item.dispatches })}
              {item.invoices ? t("variant.perInvoice", { n: num(item.dispatches / item.invoices) }) : ""}
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}
