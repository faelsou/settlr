"use client";

import { Badge, deliveryCaption, labelOf } from "@/components/status";
import { Banner, Button, Empty, Segmented, Skeleton, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { clsx, documentBr, money, phonesBr, when } from "@/lib/format";
import type { Conversation } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const FILTERS = [
  { value: "", label: "Todas" },
  { value: "agente", label: "Agente" },
  { value: "humano", label: "Humano" },
  { value: "aguardando_aprovacao", label: "Aprovação" },
];

const CLOSED = new Set(["pago", "cancelado", "renegociado"]);

export function Inbox({ activeId }: { activeId?: string }) {
  const router = useRouter();
  const [state, setState] = useState("");
  const list = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.conversations(),
    refetchInterval: 3000,
    refetchOnWindowFocus: true,
  });
  const visible = (list.data?.items ?? []).filter((item) => !state || item.state === state);
  const active = list.data?.items.find((item) => item.id === activeId);

  function open(id: string) {
    router.replace(`/conversas?id=${id}`);
  }

  return (
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-4.25rem)] overflow-hidden border-t border-paper-200 bg-white md:-mx-8 md:-my-8">
      <section className={clsx("min-h-0 w-full flex-col border-paper-200 md:flex md:w-[340px] md:border-r", activeId ? "hidden" : "flex")}>
        <div className="space-y-3 border-b border-paper-200 px-4 py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-ink-700">WhatsApp</p>
            <h1 className="font-display text-2xl">Conversas</h1>
          </div>
          <Segmented label="Estado da conversa" value={state} onChange={setState} options={FILTERS} />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {list.isPending ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 5 }, (_, index) => (
                <Skeleton key={index} className="h-16" />
              ))}
            </div>
          ) : list.isError ? (
            <div className="p-4">
              <Banner>{errorText(list.error)}</Banner>
            </div>
          ) : !visible.length ? (
            <Empty title="Nenhuma conversa" hint="O agente só aparece aqui depois que o devedor responde." />
          ) : (
            <ul>
              {visible.map((conversation) => {
                const selected = conversation.id === activeId;
                return (
                  <li key={conversation.id}>
                    <button
                      type="button"
                      onClick={() => open(conversation.id)}
                      className={clsx(
                        "flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition",
                        selected ? "bg-brand-100" : "hover:bg-paper-50",
                      )}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink-900">{conversation.debtor.name}</span>
                        <span className="mt-0.5 block truncate text-sm text-ink-700/70">
                          {conversation.summary ?? phonesBr(conversation.debtor.phones, conversation.debtor.phone)}
                        </span>
                      </span>
                      <span className="shrink-0 text-right">
                        <Badge value={conversation.state} />
                        <span className="mt-1 block text-[11px] text-ink-700/50">{when(conversation.updated_at)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      <Thread
        conversation={active}
        activeId={activeId}
        pending={list.isPending}
        onBack={() => router.replace("/conversas")}
      />
    </div>
  );
}

function Thread({
  conversation,
  activeId,
  pending,
  onBack,
}: {
  conversation: Conversation | undefined;
  activeId?: string;
  pending: boolean;
  onBack: () => void;
}) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const messages = useQuery({
    queryKey: ["messages", activeId],
    queryFn: () => api.messages(activeId!),
    enabled: Boolean(activeId),
    refetchInterval: 3000,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "labels"],
    queryFn: () => api.invoices({}),
    enabled: Boolean(conversation),
    staleTime: 15_000,
  });

  const takeover = useMutation({
    mutationFn: () => api.takeover(activeId!),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["conversations"] });
      client.invalidateQueries({ queryKey: ["messages", activeId] });
    },
  });
  const release = useMutation({
    mutationFn: () => api.release(activeId!),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["conversations"] });
      client.invalidateQueries({ queryKey: ["messages", activeId] });
    },
  });
  const send = useMutation({
    mutationFn: () => api.sendMessage(activeId!, text),
    onSuccess: () => {
      setText("");
      client.invalidateQueries({ queryKey: ["messages", activeId] });
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.data?.length, activeId]);

  if (!activeId) {
    return (
      <section className="hidden min-w-0 flex-1 items-center justify-center bg-paper-50 md:flex">
        <Empty title="Selecione uma conversa" hint="A lista à esquerda é a caixa de entrada do WhatsApp." />
      </section>
    );
  }

  if (!conversation) {
    return (
      <section className="flex min-w-0 flex-1 items-center justify-center bg-paper-50">
        {pending ? <Skeleton className="h-40 w-80" /> : <Empty title="Conversa não encontrada" />}
      </section>
    );
  }

  const openInvoices =
    invoices.data?.items.filter((invoice) => invoice.debtor.id === conversation.debtor.id && !CLOSED.has(invoice.status)) ?? [];
  const error = takeover.error ?? release.error ?? send.error;
  const human = conversation.state === "humano";

  return (
    <>
      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-paper-50">
        <header className="flex items-start justify-between gap-3 border-b border-paper-200 bg-white px-4 py-4 md:px-6">
          <div className="min-w-0">
            <button type="button" onClick={onBack} className="mb-2 text-sm font-semibold text-brand-700 md:hidden">
              ← Conversas
            </button>
            <p className="text-xs uppercase tracking-[0.18em] text-ink-700">{labelOf(conversation.intent)}</p>
            <h2 className="truncate font-display text-2xl">{conversation.debtor.name}</h2>
            <p className="mt-1 line-clamp-2 text-sm text-ink-700/70">{conversation.summary ?? "Sem resumo do agente."}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge value={conversation.state} />
            {human ? (
              <Button variant="outline" onClick={() => release.mutate()} disabled={release.isPending}>
                Devolver ao agente
              </Button>
            ) : (
              <Button onClick={() => takeover.mutate()} disabled={takeover.isPending}>
                Assumir
              </Button>
            )}
          </div>
        </header>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4 md:px-6">
          {messages.data?.map((message) => {
            const inbound = message.direction === "in";
            return (
              <div key={message.id} className={clsx("flex", inbound ? "justify-start" : "justify-end")}>
                <div
                  className={clsx(
                    "max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm md:max-w-xl",
                    inbound ? "rounded-bl-md bg-white text-ink-900" : "rounded-br-md bg-brand-700 text-white",
                  )}
                >
                  <p className={clsx("text-[11px] font-semibold", inbound ? "text-ink-700/60" : "text-white/75")}>
                    {message.author} · {when(message.created_at)}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap">{message.body}</p>
                  {deliveryCaption(message.delivery_status, message.file_status) ? (
                    <p className={clsx("mt-1 text-[11px]", inbound ? "text-ink-700/60" : "text-white/75")}>
                      {deliveryCaption(message.delivery_status, message.file_status)}
                    </p>
                  ) : null}
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
        <form
          className="border-t border-paper-200 bg-white p-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (human && text.trim()) send.mutate();
          }}
        >
          {error ? (
            <div className="mb-3">
              <Banner>{errorText(error)}</Banner>
            </div>
          ) : null}
          <div className="flex items-end gap-3">
            <Textarea
              rows={2}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={human ? "Escreva para o devedor" : "Assuma a conversa para responder"}
              disabled={!human}
            />
            <Button type="submit" disabled={!human || !text.trim() || send.isPending}>
              Enviar
            </Button>
          </div>
        </form>
      </section>
      <aside className="hidden w-80 shrink-0 flex-col border-l border-paper-200 bg-white xl:flex">
        <div className="border-b border-paper-200 px-5 py-5">
          <p className="text-xs uppercase tracking-[0.18em] text-ink-700">Devedor</p>
          <p className="mt-1 font-display text-2xl leading-tight">{conversation.debtor.name}</p>
          <p className="mt-2 text-sm text-ink-700/80">{phonesBr(conversation.debtor.phones, conversation.debtor.phone)}</p>
          <p className="text-sm text-ink-700/70">{documentBr(conversation.debtor.document)}</p>
          <p className="mt-2 text-xs text-ink-700/60">
            {conversation.identity_verified ? "Identidade confirmada" : "Identidade ainda não confirmada"}
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-700/60">Títulos em aberto</p>
          {!openInvoices.length ? (
            <p className="mt-3 text-sm text-ink-700/70">Nenhum título em aberto neste recorte.</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {openInvoices.slice(0, 6).map((invoice) => (
                <li key={invoice.id}>
                  <Link href={`/titulos/${invoice.id}`} className="block rounded-xl bg-paper-50 px-3 py-2 hover:bg-paper-100">
                    <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                      {invoice.external_id}
                      <span>{money(Number(invoice.amount) - Number(invoice.amount_paid))}</span>
                    </span>
                    <span className="mt-1 flex items-center justify-between text-xs text-ink-700/60">
                      <Badge value={invoice.status} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
