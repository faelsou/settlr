"use client";

import { Sparkline, Ticker } from "@/components/visuals";
import { Banner, Card, Segmented, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

const PERIODS = [
  { value: "7", label: "7 dias" },
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
] as const;

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
  const [, month, day] = value.split("-");
  return `${day}/${month}`;
}

function lateHint(current: number | null, baseline: number | null): string {
  if (baseline == null) return "Depois do vencimento";
  const base = baseline.toFixed(1).replace(".", ",");
  if (current == null) return `Linha de base da implantação: ${base} dias`;
  const diff = current - baseline;
  const gap = Math.abs(diff).toFixed(1).replace(".", ",");
  if (diff < -0.05) return `${gap} dias abaixo da linha de base (${base})`;
  if (diff > 0.05) return `${gap} dias acima da linha de base (${base})`;
  return `Na linha de base (${base})`;
}

function deltaText(current: number | null | undefined, previous: number | null | undefined): string | null {
  if (current == null || previous == null) return null;
  const points = Math.abs((current - previous) * 100).toFixed(1).replace(".", ",");
  if (current - previous > 0.0001) return `${points} p.p. acima da semana anterior`;
  if (previous - current > 0.0001) return `${points} p.p. abaixo da semana anterior`;
  return "Estável em relação à semana anterior";
}

export function MetricsBoard({ periodControl = false }: { periodControl?: boolean }) {
  const [days, setDays] = useState<(typeof PERIODS)[number]["value"]>("30");
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
          {data ? `Período ${data.period_start} → ${data.period_end}` : "Últimos 30 dias"}
        </p>
        {periodControl ? (
          <Segmented label="Período" value={days} onChange={setDays} options={[...PERIODS]} />
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
            title="Taxa de recuperação"
            value={data.recovery_rate}
            format={pct}
            hint={`${money(data.recovered_amount)} de ${money(data.overdue_amount)} vencidos`}
            series={points?.map((point) => point.recovery_rate) ?? null}
            labels={points ? [weekLabel(points[0].period_start), weekLabel(points[points.length - 1].period_end)] : undefined}
            delta={deltaText(points?.at(-1)?.recovery_rate, points?.at(-2)?.recovery_rate)}
            seriesPending={series.isPending}
          />
          <TrendCard
            className="md:col-span-2"
            title="Baixa automática"
            value={data.auto_reconciliation_rate}
            format={pct}
            hint={`${data.auto_reconciled} de ${data.payments_reconciled} pagamentos`}
            series={points?.map((point) => point.auto_reconciliation_rate) ?? null}
            labels={points ? [weekLabel(points[0].period_start), weekLabel(points[points.length - 1].period_end)] : undefined}
            delta={deltaText(points?.at(-1)?.auto_reconciliation_rate, points?.at(-2)?.auto_reconciliation_rate)}
            seriesPending={series.isPending}
          />
          <Stat
            title="Dias médios de atraso"
            value={data.avg_days_late}
            format={(value) => value.toFixed(1)}
            hint={lateHint(data.avg_days_late, data.baseline_avg_days_late)}
          />
          <Stat
            title="Promessas cumpridas"
            value={data.promise_kept_rate}
            format={pct}
            hint={`${data.promises_kept} de ${data.promises_made}`}
          />
          <Stat title="Exceções abertas" value={data.exceptions_open} format={(value) => String(Math.round(value))} hint="Fila curta indica matching bom" />
          <Stat
            title="Tempo médio de resolução"
            value={data.avg_exception_resolution_hours}
            format={(value) => `${value.toFixed(1)} h`}
            hint="Exceções fechadas no período"
          />
        </div>
      )}
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
      <p className="text-xs uppercase tracking-wide text-ink-700/60">{title}</p>
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
      <p className="text-xs uppercase tracking-wide text-ink-700/60">{title}</p>
      <p className="mt-2 font-display text-3xl tracking-tight">{value == null ? "—" : <Ticker value={value} format={format} />}</p>
      <p className="mt-2 text-sm text-ink-700/70">{hint}</p>
    </Card>
  );
}
