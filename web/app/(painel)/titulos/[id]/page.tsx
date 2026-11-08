"use client";

import { Badge, labelOf } from "@/components/status";
import { useToast } from "@/components/toast";
import { Banner, Breadcrumb, Button, Card, Field, Input, Skeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { day, documentBr, money, phonesBr, when } from "@/lib/format";
import type { Debtor } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

const MAX_WHATSAPP = 5;

function nationalPhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.startsWith("55") && (digits.length === 12 || digits.length === 13)) return digits.slice(2);
  return digits || value;
}

function fieldsFrom(debtor: Debtor): string[] {
  const stored = (debtor.phones?.length ? debtor.phones : debtor.phone ? [debtor.phone] : []).map(nationalPhone);
  return stored.length ? stored : [""];
}

function WhatsAppNumbers({ debtor }: { debtor: Debtor }) {
  const client = useQueryClient();
  const toast = useToast();
  const savedKey = [debtor.id, ...(debtor.phones ?? []), debtor.phone ?? ""].join("|");
  const [numbers, setNumbers] = useState<string[]>(() => fieldsFrom(debtor));

  useEffect(() => {
    setNumbers(fieldsFrom(debtor));
  }, [savedKey, debtor]);

  const save = useMutation({
    mutationFn: () =>
      api.saveWhatsappNumbers(
        debtor.id,
        numbers.map((item) => item.trim()).filter(Boolean),
      ),
    onSuccess: (saved) => {
      const next = (saved.phones?.length ? saved.phones : saved.phone ? [saved.phone] : []).map(nationalPhone);
      setNumbers(next.length ? next : [""]);
      toast("Números gravados. A régua dispara para cada um deles.");
      client.invalidateQueries({ queryKey: ["invoice"] });
    },
  });

  return (
    <Card className="space-y-4 p-6">
      <div>
        <h2 className="font-display text-xl">WhatsApp</h2>
        <p className="mt-1 text-sm text-ink-700/70">
          Até {MAX_WHATSAPP} celulares de quem paga. A mesma cobrança sai para todos. Vale para os títulos deste devedor.
        </p>
      </div>
      {save.isError ? <Banner>{errorText(save.error)}</Banner> : null}
      <div className="grid gap-3 md:grid-cols-2">
        {numbers.map((value, index) => (
          <Field key={index} label={`WhatsApp ${index + 1}`}>
            <div className="flex gap-2">
              <Input
                inputMode="tel"
                placeholder="11988887777"
                value={value}
                onChange={(event) => {
                  const next = [...numbers];
                  next[index] = event.target.value;
                  setNumbers(next);
                }}
              />
              {numbers.length > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setNumbers(numbers.filter((_, item) => item !== index))}
                >
                  Tirar
                </Button>
              ) : null}
            </div>
          </Field>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {numbers.length < MAX_WHATSAPP ? (
          <Button type="button" variant="outline" onClick={() => setNumbers([...numbers, ""])}>
            Adicionar número
          </Button>
        ) : null}
        <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Salvando…" : "Salvar WhatsApp"}
        </Button>
      </div>
    </Card>
  );
}

export default function TituloDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const invoice = useQuery({ queryKey: ["invoice", id], queryFn: () => api.invoice(id) });
  const data = invoice.data;

  if (invoice.isError) return <Banner>{errorText(invoice.error)}</Banner>;
  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const openAmount = Number(data.amount) - Number(data.amount_paid);

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ href: "/titulos", label: "Títulos" }, { label: data.debtor.name }]} />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-ink-700">{data.external_id}</p>
          <h1 className="font-display text-3xl tracking-tight">{data.debtor.name}</h1>
          <p className="mt-1 text-sm text-ink-700/70">
            {documentBr(data.debtor.document)} · {phonesBr(data.debtor.phones, data.debtor.phone)}
            {data.debtor.opt_out ? " · opt-out" : ""}
          </p>
        </div>
        <Badge value={data.status} />
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-ink-700/60">Valor</p>
          <p className="mt-1 font-display text-2xl">{money(data.amount)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-ink-700/60">Em aberto</p>
          <p className="mt-1 font-display text-2xl">{money(openAmount)}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs uppercase tracking-wide text-ink-700/60">Vencimento</p>
          <p className="mt-1 font-display text-2xl">{day(data.due_date)}</p>
        </Card>
      </div>

      {data.has_payment_code ? null : (
        <Banner tone="ok">
          Este título não entra na régua até chegar o PIX ou o boleto. Quando o código chegar, sai só a etapa do dia.
        </Banner>
      )}

      <WhatsAppNumbers debtor={data.debtor} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="font-display text-xl">Régua</h2>
          {!data.dunning_events.length ? (
            <p className="mt-3 text-sm text-ink-700/70">Nenhum disparo ainda.</p>
          ) : (
            <ol className="mt-5">
              {data.dunning_events.map((ev, index) => (
                <li key={`${ev.step}-${ev.channel}-${ev.sent_at}`} className="relative flex gap-3 pb-4">
                  {index < data.dunning_events.length - 1 ? (
                    <span className="absolute left-[6px] top-4 h-[calc(100%-8px)] w-px bg-paper-200" />
                  ) : null}
                  <span className="relative mt-1 h-3.5 w-3.5 shrink-0 rounded-full bg-brand-700" />
                  <span>
                    <span className="block text-sm font-semibold">
                      {ev.step} · {ev.channel}
                    </span>
                    <span className="text-xs text-ink-700/60">
                      {when(ev.sent_at)} · {ev.delivery_status}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <Card className="p-6">
          <h2 className="font-display text-xl">Promessas e matches</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {data.promises.map((p) => (
              <li key={p.promised_date}>
                Promessa para {day(p.promised_date)} · {p.fulfilled === null ? "em aberto" : p.fulfilled ? "cumprida" : "quebrada"}
              </li>
            ))}
            {data.matches.map((m) => (
              <li key={`${m.payment_id}-${m.invoice_id}`}>
                {money(m.amount_applied)} via {labelOf(m.method)}
                {m.provisional ? " (provisório)" : ""} · {m.confirmed_by}
              </li>
            ))}
            {!data.promises.length && !data.matches.length ? (
              <li className="text-ink-700/70">Sem promessa e sem baixa ainda.</li>
            ) : null}
          </ul>
        </Card>
      </div>

      {data.installments.length > 0 ? (
        <Card className="p-6">
          <h2 className="font-display text-xl">Parcelas do acordo</h2>
          <ul className="mt-4 space-y-2 text-sm">
            {data.installments.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 border-b border-paper-100 pb-2">
                <Link href={`/titulos/${item.id}`} className="font-semibold hover:underline">
                  {item.description ?? item.external_id}
                </Link>
                <span>{money(item.amount)}</span>
                <span>{day(item.due_date)}</span>
                <Badge value={item.status} />
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card className="p-6">
        <h2 className="font-display text-xl">Conversa do devedor</h2>
        {!data.messages.length ? (
          <p className="mt-3 text-sm text-ink-700/70">Nenhuma mensagem nesta conversa.</p>
        ) : (
          <div className="mt-4 max-h-96 space-y-3 overflow-y-auto">
            {data.messages.map((m) => {
              const inbound = m.direction === "in";
              return (
                <div key={m.id} className={inbound ? "flex justify-start" : "flex justify-end"}>
                  <div
                    className={
                      inbound
                        ? "max-w-xl rounded-2xl rounded-bl-md bg-paper-100 px-4 py-3 text-sm"
                        : "max-w-xl rounded-2xl rounded-br-md bg-brand-700 px-4 py-3 text-sm text-white"
                    }
                  >
                    <p className={inbound ? "text-[11px] font-semibold text-ink-700/60" : "text-[11px] font-semibold text-white/75"}>
                      {inbound ? "Devedor" : m.author} · {when(m.created_at)}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
