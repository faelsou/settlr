"use client";

import { Badge } from "@/components/status";
import { MetricsBoard } from "@/components/metrics-board";
import { Card, PageHeader, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { money, when } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";

export default function InicioPage() {
  const { t } = useI18n();
  const exceptions = useQuery({
    queryKey: ["exceptions", "aberta"],
    queryFn: () => api.exceptions("aberta"),
    refetchInterval: 15000,
  });
  const approvals = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.approvals(),
    refetchInterval: 15000,
  });
  const conversations = useQuery({
    queryKey: ["conversations", "humano"],
    queryFn: () => api.conversations("humano"),
    refetchInterval: 15000,
  });
  const deliveries = useQuery({
    queryKey: ["deliveries", "falhou"],
    queryFn: () => api.deliveries(true),
    refetchInterval: 15000,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("home.eyebrow")}
        title={t("nav.panel")}
        hint={t("home.hint")}
      />
      <MetricsBoard />
      <div className="grid gap-4 lg:grid-cols-2">
        <Queue
          title={t("home.excTitle")}
          href="/excecoes"
          pending={exceptions.isPending}
          error={exceptions.isError ? errorText(exceptions.error) : null}
          empty={t("home.excEmpty")}
        >
          {exceptions.data?.items.slice(0, 5).map((item) => (
            <Link key={item.id} href="/excecoes" className="flex items-center justify-between gap-3 py-3">
              <span className="min-w-0">
                <Badge value={item.type} />
                <span className="mt-1 block truncate text-sm text-ink-700/80">
                  {item.payment ? `${money(item.payment.amount)} · ${item.payment.payer_name ?? t("home.noName")}` : t("home.noPayment")}
                </span>
              </span>
              <span className="shrink-0 text-xs text-ink-700/50">{when(item.created_at)}</span>
            </Link>
          ))}
        </Queue>
        <Queue
          title={t("home.humanTitle")}
          href="/conversas"
          pending={conversations.isPending}
          error={conversations.isError ? errorText(conversations.error) : null}
          empty={t("home.humanEmpty")}
        >
          {conversations.data?.items.slice(0, 5).map((item) => (
            <Link key={item.id} href={`/conversas?id=${item.id}`} className="block py-3">
              <span className="font-semibold">{item.debtor.name}</span>
              <span className="mt-0.5 block truncate text-sm text-ink-700/70">{item.summary ?? t("home.noSummary")}</span>
            </Link>
          ))}
        </Queue>
        <Queue
          title={t("home.failTitle")}
          href="/entregas"
          pending={deliveries.isPending}
          error={deliveries.isError ? errorText(deliveries.error) : null}
          empty={t("home.failEmpty")}
        >
          {deliveries.data?.items.slice(0, 5).map((item) => (
            <Link key={item.id} href={`/conversas?id=${item.conversation_id}`} className="flex items-center justify-between gap-3 py-3">
              <span className="min-w-0">
                <span className="font-semibold">{item.debtor_name}</span>
                <span className="mt-0.5 block truncate text-sm text-ink-700/70">
                  {item.body === "[comprovante]" ? t("home.receipt") : item.body ?? t("home.noText")}
                </span>
              </span>
              <Badge value={item.delivery_status} />
            </Link>
          ))}
        </Queue>
        <Queue
          title={t("nav.aprovacoes")}
          href="/aprovacoes"
          pending={approvals.isPending}
          error={approvals.isError ? errorText(approvals.error) : null}
          empty={t("home.apprEmpty")}
        >
          {approvals.data?.slice(0, 5).map((item) => (
            <Link key={item.id} href="/aprovacoes" className="block py-3">
              <span className="font-semibold">{item.debtor.name}</span>
              <span className="mt-0.5 block truncate text-sm text-ink-700/70">{item.reason}</span>
            </Link>
          ))}
        </Queue>
      </div>
    </div>
  );
}

function Queue({
  title,
  href,
  pending,
  error,
  empty,
  children,
}: {
  title: string;
  href: string;
  pending: boolean;
  error: string | null;
  empty: string;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const items = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-display text-xl">{title}</h2>
        <Link href={href} className="text-sm font-semibold text-brand-700">
          {t("home.open")}
        </Link>
      </div>
      {error ? <p className="mt-3 text-sm text-red-800">{error}</p> : null}
      {pending ? (
        <div className="mt-4 space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : items.length ? (
        <div className="mt-2 divide-y divide-paper-100">{children}</div>
      ) : error ? null : (
        <p className="mt-4 text-sm text-ink-700/70">{empty}</p>
      )}
    </Card>
  );
}
