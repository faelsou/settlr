"use client";

import { useToast } from "@/components/toast";
import { Banner, Button, Card, Field, Input, PageHeader, Segmented, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import type { TenantSettings } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const MAX_SENDERS = 5;

type Sender = { instance: string; number: string };

function national(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.startsWith("55") && (digits.length === 12 || digits.length === 13)) return digits.slice(2);
  return value;
}

function fromSaved(list: Sender[] | undefined): Sender[] {
  if (!list?.length) return [{ instance: "", number: "" }];
  return list.map((item) => ({ instance: item.instance, number: national(item.number) }));
}

export default function ConfiguracoesPage() {
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<TenantSettings | null>(null);
  const [section, setSection] = useState("disparo");
  const [senders, setSenders] = useState<Sender[]>([{ instance: "", number: "" }]);
  const [senderError, setSenderError] = useState<string | null>(null);

  useEffect(() => {
    if (!query.data) return;
    setForm((current) => (current ? { ...current, whatsapp_senders: query.data?.whatsapp_senders } : query.data));
    setSenders(fromSaved(query.data.whatsapp_senders));
  }, [query.data]);

  const save = useMutation({
    mutationFn: () => api.saveSettings(form!),
    onSuccess: (data) => {
      setForm(data);
      toast("Configurações gravadas. A régua e o agente passam a usar estes limites.");
    },
  });

  const saveSenders = useMutation({
    mutationFn: (rows: Sender[]) => api.saveWhatsappSenders(rows),
    onSuccess: (saved) => {
      setSenders(fromSaved(saved));
      setSenderError(null);
      toast("Números gravados. O primeiro da lista dispara as cobranças.");
      client.setQueryData<TenantSettings>(["settings"], (current) =>
        current ? { ...current, whatsapp_senders: saved } : current,
      );
    },
  });

  function onSaveSenders() {
    const rows = senders.map((item) => ({ instance: item.instance.trim(), number: item.number.trim() }));
    const half = rows.some((item) => (item.instance && !item.number) || (!item.instance && item.number));
    if (half) {
      setSenderError("Preencha a instância e o número, ou apague a linha.");
      return;
    }
    setSenderError(null);
    saveSenders.mutate(rows.filter((item) => item.instance && item.number));
  }

  if (!form) return <p className="text-sm text-ink-700/70">Carregando configurações…</p>;

  const policy = form.negotiation_policy;
  const hours = form.allowed_hours;
  const recon = form.reconciliation_rules;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Tenant"
        title="Configurações"
        hint="Política, régua e horário. O agente só oferece o que cabe aqui — nunca inventa valor."
      />

      {save.isError ? <Banner>{errorText(save.error)}</Banner> : null}

      <Segmented
        label="Seção das configurações"
        value={section}
        onChange={setSection}
        options={[
          { value: "disparo", label: "Disparo" },
          { value: "politica", label: "Política" },
          { value: "horario", label: "Horário" },
          { value: "conciliacao", label: "Conciliação" },
          { value: "regua", label: "Régua" },
        ]}
      />

      {section === "disparo" ? (
      <Card className="space-y-4 p-6">
        <div>
          <h2 className="font-display text-xl">Números de disparo</h2>
          <p className="mt-1 text-sm text-ink-700/70">
            Até {MAX_SENDERS} WhatsApps da empresa. O primeiro envia as cobranças. Se um número cair, apague e cadastre outro.
          </p>
        </div>
        {senderError ? <Banner>{senderError}</Banner> : null}
        {saveSenders.isError ? <Banner>{errorText(saveSenders.error)}</Banner> : null}
        <div className="space-y-4">
          {senders.map((sender, index) => (
            <div key={index} className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <Field label={index === 0 ? "Instância em disparo" : `Instância ${index + 1}`}>
                <Input
                  value={sender.instance}
                  placeholder="nome-na-evolution"
                  onChange={(event) => {
                    const next = [...senders];
                    next[index] = { ...sender, instance: event.target.value };
                    setSenders(next);
                  }}
                />
              </Field>
              <Field label={index === 0 ? "Número em disparo" : `Número ${index + 1}`}>
                <Input
                  inputMode="tel"
                  value={sender.number}
                  placeholder="11988887777"
                  onChange={(event) => {
                    const next = [...senders];
                    next[index] = { ...sender, number: event.target.value };
                    setSenders(next);
                  }}
                />
              </Field>
              <div className="flex gap-2">
                {index > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const next = [...senders];
                      const [chosen] = next.splice(index, 1);
                      setSenders([chosen, ...next]);
                    }}
                  >
                    Usar este
                  </Button>
                ) : null}
                {senders.length > 1 ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setSenders(senders.filter((_, item) => item !== index))}
                  >
                    Tirar
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {senders.length < MAX_SENDERS ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => setSenders([...senders, { instance: "", number: "" }])}
            >
              Adicionar número
            </Button>
          ) : null}
          <Button type="button" onClick={onSaveSenders} disabled={saveSenders.isPending}>
            {saveSenders.isPending ? "Salvando…" : "Salvar números"}
          </Button>
        </div>
      </Card>
      ) : null}

      {section === "politica" ? (
      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Política de negociação</h2>
        <Field label="Desconto máx. à vista (%)">
          <Input
            value={policy.max_discount_pct_cash}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_discount_pct_cash: e.target.value } })
            }
          />
        </Field>
        <Field label="Entrada mínima (%)">
          <Input
            value={policy.min_down_payment_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_down_payment_pct: e.target.value } })
            }
          />
        </Field>
        <Field label="Máx. de parcelas">
          <Input
            type="number"
            value={policy.max_installments}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_installments: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Parcela mínima (R$)">
          <Input
            value={policy.min_installment_amount}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_installment_amount: e.target.value } })
            }
          />
        </Field>
        <Field label="Juros ao mês (%)">
          <Input
            value={policy.monthly_interest_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, monthly_interest_pct: e.target.value } })
            }
          />
        </Field>
        <Field label="Promessa máxima (dias)">
          <Input
            type="number"
            value={policy.max_promise_days}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_promise_days: Number(e.target.value) } })
            }
          />
        </Field>
      </Card>
      ) : null}

      {section === "horario" ? (
      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Horário permitido (CDC)</h2>
        <Field label="Início">
          <Input
            type="time"
            value={hours.start.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, start: e.target.value } })}
          />
        </Field>
        <Field label="Fim">
          <Input
            type="time"
            value={hours.end.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, end: e.target.value } })}
          />
        </Field>
        <div className="md:col-span-2 flex flex-wrap gap-2">
          {WEEKDAYS.map((label, idx) => {
            const on = hours.weekdays.includes(idx);
            return (
              <button
                key={label}
                type="button"
                onClick={() => {
                  const next = on ? hours.weekdays.filter((d) => d !== idx) : [...hours.weekdays, idx].sort();
                  setForm({ ...form, allowed_hours: { ...hours, weekdays: next } });
                }}
                className={`rounded-full px-3 py-1 text-sm ${on ? "bg-brand-700 text-white" : "bg-paper-100 text-ink-800"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <Field label="Fuso">
          <Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
        </Field>
      </Card>
      ) : null}

      {section === "conciliacao" ? (
      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">Conciliação</h2>
        <Field label="Dias antes do vencimento">
          <Input
            type="number"
            value={recon.days_before_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_before_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Dias depois do vencimento">
          <Input
            type="number"
            value={recon.days_after_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_after_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label="Sobrepagamento máx. (%)">
          <Input
            value={recon.max_overpay_pct}
            onChange={(e) => setForm({ ...form, reconciliation_rules: { ...recon, max_overpay_pct: e.target.value } })}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm md:col-span-2">
          <input
            type="checkbox"
            className="accent-brand-700"
            checked={recon.allow_partial}
            onChange={(e) => setForm({ ...form, reconciliation_rules: { ...recon, allow_partial: e.target.checked } })}
          />
          Permitir baixa parcial
        </label>
      </Card>
      ) : null}

      {section === "regua" ? (
      <Card className="space-y-4 p-6">
        <div>
          <h2 className="font-display text-xl">Templates da régua</h2>
          <p className="mt-1 text-sm text-ink-700/70">
            O texto é o da resposta e do e-mail. O WhatsApp da régua só sai com o template oficial
            aprovado na Meta, no nome preenchido abaixo. Sem esse template e sem o número pareado, a conta não liga a régua.
          </p>
        </div>
        {Object.entries(form.dunning_rules.templates).map(([key, value], index) => {
          const official = form.dunning_rules.whatsapp_templates?.[key] ?? {
            name: "",
            language: "pt_BR",
            params: [],
          };
          const setOfficial = (patch: Partial<typeof official>) =>
            setForm({
              ...form,
              dunning_rules: {
                ...form.dunning_rules,
                whatsapp_templates: {
                  ...form.dunning_rules.whatsapp_templates,
                  [key]: { ...official, ...patch },
                },
              },
            });
          return (
            <div key={key} className={index === 0 ? "space-y-3" : "space-y-3 border-t border-paper-200 pt-4"}>
              <Field label={`${key} — texto da resposta e do e-mail`}>
                <Textarea
                  rows={3}
                  value={value}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      dunning_rules: {
                        ...form.dunning_rules,
                        templates: { ...form.dunning_rules.templates, [key]: e.target.value },
                      },
                    })
                  }
                />
              </Field>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="Template oficial (nome na Meta)">
                  <Input value={official.name} placeholder="lembrete_pix" onChange={(e) => setOfficial({ name: e.target.value })} />
                </Field>
                <Field label="Idioma do template">
                  <Input value={official.language} placeholder="pt_BR" onChange={(e) => setOfficial({ language: e.target.value })} />
                </Field>
              </div>
            </div>
          );
        })}
      </Card>
      ) : null}

      {section === "disparo" ? null : (
      <Button onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? "Salvando…" : "Salvar configurações"}
      </Button>
      )}
    </div>
  );
}
