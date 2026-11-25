"use client";

import { useToast } from "@/components/toast";
import { Banner, Button, Card, Field, Input, PageHeader, Segmented, Textarea } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { canConfigure, roleLabel } from "@/lib/roles";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/messages";
import type { TenantSettings } from "@/lib/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

const WEEKDAYS: MessageKey[] = ["day.0", "day.1", "day.2", "day.3", "day.4", "day.5", "day.6"];
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
  const { t } = useI18n();
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const [form, setForm] = useState<TenantSettings | null>(null);
  const [section, setSection] = useState("disparo");
  const [senders, setSenders] = useState<Sender[]>([{ instance: "", number: "" }]);
  const [senderError, setSenderError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("financeiro");
  const locked = me.data ? !canConfigure(me.data.role) : false;

  useEffect(() => {
    if (!query.data) return;
    setForm((current) => (current ? { ...current, whatsapp_senders: query.data?.whatsapp_senders } : query.data));
    setSenders(fromSaved(query.data.whatsapp_senders));
  }, [query.data]);

  const save = useMutation({
    mutationFn: () => api.saveSettings(form!),
    onSuccess: (data) => {
      setForm(data);
      toast(t("cfg.saved"));
    },
  });

  const saveSenders = useMutation({
    mutationFn: (rows: Sender[]) => api.saveWhatsappSenders(rows),
    onSuccess: (saved) => {
      setSenders(fromSaved(saved));
      setSenderError(null);
      toast(t("cfg.sendersSaved"));
      client.setQueryData<TenantSettings>(["settings"], (current) =>
        current ? { ...current, whatsapp_senders: saved } : current,
      );
    },
  });

  const activate = useMutation({
    mutationFn: async () => {
      const saved = await api.saveSettings(form!);
      setForm(saved);
      return api.activate();
    },
    onSuccess: (data) => {
      setForm(data);
      toast(data.active ? t("cfg.active") : t("cfg.notYet"));
    },
  });

  const team = useQuery({
    queryKey: ["members"],
    queryFn: api.members,
    enabled: section === "equipe" && canConfigure(me.data?.role),
  });

  const invite = useMutation({
    mutationFn: () => api.invite(inviteEmail.trim(), inviteRole),
    onSuccess: (member) => {
      setInviteEmail("");
      toast(
        member.delivered
          ? t("cfg.inviteSent")
          : t("cfg.inviteNoSmtp"),
      );
      client.invalidateQueries({ queryKey: ["members"] });
    },
  });

  function onSaveSenders() {
    const rows = senders.map((item) => ({ instance: item.instance.trim(), number: item.number.trim() }));
    const half = rows.some((item) => (item.instance && !item.number) || (!item.instance && item.number));
    if (half) {
      setSenderError(t("cfg.halfRow"));
      return;
    }
    setSenderError(null);
    saveSenders.mutate(rows.filter((item) => item.instance && item.number));
  }

  if (!form) return <p className="text-sm text-ink-700/70">{t("cfg.loading")}</p>;

  const policy = form.negotiation_policy;
  const hours = form.allowed_hours;
  const recon = form.reconciliation_rules;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={t("cfg.eyebrow")}
        title={t("nav.configuracoes")}
        hint={t("cfg.hint")}
      />

      {locked ? (
        <Banner>{t("cfg.locked")}</Banner>
      ) : null}
      {save.isError ? <Banner>{errorText(save.error)}</Banner> : null}
      {activate.isError ? <Banner>{errorText(activate.error)}</Banner> : null}

      <Segmented
        label={t("cfg.sectionLabel")}
        value={section}
        onChange={setSection}
        options={[
          { value: "disparo", label: t("cfg.sending") },
          { value: "politica", label: t("onb.policy") },
          { value: "horario", label: t("onb.hours") },
          { value: "conciliacao", label: t("pay.eyebrow") },
          { value: "regua", label: t("onb.ruler") },
          ...(!locked
            ? [
                { value: "conta", label: t("cfg.account") },
                { value: "equipe", label: t("cfg.team") },
              ]
            : []),
        ]}
      />

      <fieldset disabled={locked} className="space-y-6 border-0 p-0">

      {section === "disparo" ? (
      <>
      <Card className="space-y-4 p-6">
        <div>
          <h2 className="font-display text-xl">{t("cfg.senders")}</h2>
          <p className="mt-1 text-sm text-ink-700/70">
            {t("cfg.sendersHint", { max: MAX_SENDERS })}
          </p>
        </div>
        {senderError ? <Banner>{senderError}</Banner> : null}
        {saveSenders.isError ? <Banner>{errorText(saveSenders.error)}</Banner> : null}
        <div className="space-y-4">
          {senders.map((sender, index) => (
            <div key={index} className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <Field label={index === 0 ? t("cfg.instanceActive") : t("cfg.instanceN", { n: index + 1 })}>
                <Input
                  value={sender.instance}
                  placeholder={t("onb.instancePh")}
                  onChange={(event) => {
                    const next = [...senders];
                    next[index] = { ...sender, instance: event.target.value };
                    setSenders(next);
                  }}
                />
              </Field>
              <Field label={index === 0 ? t("cfg.numberActive") : t("cfg.numberN", { n: index + 1 })}>
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
                    {t("cfg.useThis")}
                  </Button>
                ) : null}
                {senders.length > 1 ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setSenders(senders.filter((_, item) => item !== index))}
                  >
                    {t("det.remove")}
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
              {t("det.addNumber")}
            </Button>
          ) : null}
          <Button type="button" onClick={onSaveSenders} disabled={saveSenders.isPending}>
            {saveSenders.isPending ? t("ui.saving") : t("cfg.saveNumbers")}
          </Button>
        </div>
      </Card>
      <Card className="space-y-4 p-6">
        <div>
          <h2 className="font-display text-xl">{t("cfg.alert")}</h2>
          <p className="mt-1 text-sm text-ink-700/70">
            {t("cfg.alertHint")}
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t("onb.ownerEmail")}>
            <Input
              type="email"
              value={form.owner_email ?? ""}
              placeholder={t("cfg.ownerEmailPh")}
              onChange={(event) => setForm({ ...form, owner_email: event.target.value })}
            />
          </Field>
          <Field label={t("cfg.ownerWa")}>
            <Input
              inputMode="tel"
              value={form.owner_phone ?? ""}
              placeholder="11988887777"
              onChange={(event) => setForm({ ...form, owner_phone: event.target.value })}
            />
          </Field>
        </div>
        <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? t("ui.saving") : t("cfg.saveAlert")}
        </Button>
      </Card>
      </>
      ) : null}

      {section === "politica" ? (
      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">{t("cfg.policyTitle")}</h2>
        <Field label={t("onb.maxDiscount")}>
          <Input
            value={policy.max_discount_pct_cash}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_discount_pct_cash: e.target.value } })
            }
          />
        </Field>
        <Field label={t("cfg.minDown")}>
          <Input
            value={policy.min_down_payment_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_down_payment_pct: e.target.value } })
            }
          />
        </Field>
        <Field label={t("onb.maxInstallments")}>
          <Input
            type="number"
            value={policy.max_installments}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, max_installments: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label={t("cfg.minInstallment")}>
          <Input
            value={policy.min_installment_amount}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, min_installment_amount: e.target.value } })
            }
          />
        </Field>
        <Field label={t("cfg.interest")}>
          <Input
            value={policy.monthly_interest_pct}
            onChange={(e) =>
              setForm({ ...form, negotiation_policy: { ...policy, monthly_interest_pct: e.target.value } })
            }
          />
        </Field>
        <Field label={t("cfg.maxPromise")}>
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
        <h2 className="font-display text-xl md:col-span-2">{t("cfg.hoursTitle")}</h2>
        <Field label={t("onb.start")}>
          <Input
            type="time"
            value={hours.start.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, start: e.target.value } })}
          />
        </Field>
        <Field label={t("onb.end")}>
          <Input
            type="time"
            value={hours.end.slice(0, 5)}
            onChange={(e) => setForm({ ...form, allowed_hours: { ...hours, end: e.target.value } })}
          />
        </Field>
        <div className="md:col-span-2 flex flex-wrap gap-2">
          {WEEKDAYS.map((dayKey, idx) => {
            const on = hours.weekdays.includes(idx);
            return (
              <button
                key={dayKey}
                type="button"
                onClick={() => {
                  const next = on ? hours.weekdays.filter((d) => d !== idx) : [...hours.weekdays, idx].sort();
                  setForm({ ...form, allowed_hours: { ...hours, weekdays: next } });
                }}
                className={`rounded-full px-3 py-1 text-sm ${on ? "bg-brand-700 text-white" : "bg-paper-100 text-ink-800"}`}
              >
                {t(dayKey)}
              </button>
            );
          })}
        </div>
        <Field label={t("cfg.timezone")}>
          <Input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
        </Field>
      </Card>
      ) : null}

      {section === "conciliacao" ? (
      <Card className="grid gap-4 p-6 md:grid-cols-2">
        <h2 className="font-display text-xl md:col-span-2">{t("pay.eyebrow")}</h2>
        <Field label={t("cfg.daysBefore")}>
          <Input
            type="number"
            value={recon.days_before_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_before_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label={t("cfg.daysAfter")}>
          <Input
            type="number"
            value={recon.days_after_due}
            onChange={(e) =>
              setForm({ ...form, reconciliation_rules: { ...recon, days_after_due: Number(e.target.value) } })
            }
          />
        </Field>
        <Field label={t("cfg.overpay")}>
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
          {t("cfg.partial")}
        </label>
      </Card>
      ) : null}

      {section === "regua" ? (
      <Card className="space-y-4 p-6">
        <div>
          <h2 className="font-display text-xl">{t("cfg.templates")}</h2>
          <p className="mt-1 text-sm text-ink-700/70">
            {t("cfg.templatesHint")}
            {form.dunning_rules.text_version ? t("cfg.textVersion", { v: form.dunning_rules.text_version }) : ""}
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
              <Field label={t("cfg.templateText", { key })}>
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
                <Field label={t("cfg.officialName")}>
                  <Input value={official.name} placeholder="kitou_lembrete" onChange={(e) => setOfficial({ name: e.target.value })} />
                </Field>
                <Field label={t("cfg.templateLang")}>
                  <Input value={official.language} placeholder="pt_BR" onChange={(e) => setOfficial({ language: e.target.value })} />
                </Field>
              </div>
              <Field label={t("cfg.params")}>
                <Input
                  value={(official.params ?? []).join(", ")}
                  placeholder="{nome}, {descricao}, {valor}, {vencimento}, {pix}"
                  onChange={(e) =>
                    setOfficial({
                      params: e.target.value
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Field>
            </div>
          );
        })}
      </Card>
      ) : null}

      {section === "disparo" || section === "conta" || section === "equipe" ? null : (
      <Button onClick={() => save.mutate()} disabled={save.isPending}>
        {save.isPending ? t("ui.saving") : t("cfg.saveSettings")}
      </Button>
      )}
      </fieldset>

      {!locked && section === "conta" ? (
        <Card className="space-y-4 p-6">
          <div>
            <h2 className="font-display text-xl">{t("cfg.account")}</h2>
            <p className="mt-1 text-sm text-ink-700/70">
              {t("cfg.accountHint")}
              {form.active ? t("cfg.isActive") : t("cfg.notActive")}
            </p>
          </div>
          {form.missing?.length ? <Banner>{t("onb.missing", { list: form.missing.join(", ") })}</Banner> : null}
          <Field label={t("onb.legal")}>
            <Textarea
              rows={3}
              value={form.legal_basis ?? ""}
              placeholder={t("cfg.legalPh")}
              onChange={(event) => setForm({ ...form, legal_basis: event.target.value })}
            />
          </Field>
          <Button type="button" onClick={() => activate.mutate()} disabled={activate.isPending}>
            {activate.isPending ? t("onb.activating") : t("cfg.saveActivate")}
          </Button>
        </Card>
      ) : null}

      {!locked && section === "equipe" ? (
        <Card className="space-y-4 p-6">
          <div>
            <h2 className="font-display text-xl">{t("cfg.team")}</h2>
            <p className="mt-1 text-sm text-ink-700/70">
              {t("cfg.teamHint")}
            </p>
          </div>
          {invite.isError ? <Banner>{errorText(invite.error)}</Banner> : null}
          <div className="grid gap-3 md:grid-cols-[1fr_180px_auto] md:items-end">
            <Field label={t("login.email")}>
              <Input
                type="email"
                value={inviteEmail}
                placeholder={t("cfg.inviteEmailPh")}
                onChange={(event) => setInviteEmail(event.target.value)}
              />
            </Field>
            <Field label={t("cfg.role")}>
              <select
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value)}
                className="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm text-ink-900"
              >
                <option value="financeiro">{roleLabel("financeiro")}</option>
                <option value="atendente">{roleLabel("atendente")}</option>
                <option value="dono">{roleLabel("dono")}</option>
              </select>
            </Field>
            <Button type="button" onClick={() => invite.mutate()} disabled={invite.isPending || !inviteEmail.trim()}>
              {invite.isPending ? t("cfg.sendingInvite") : t("cfg.sendInvite")}
            </Button>
          </div>
          <ul className="divide-y divide-paper-200 text-sm">
            {(team.data ?? []).map((member) => (
              <li key={member.id} className="flex items-center justify-between py-2">
                <span>{member.email}</span>
                <span className="text-ink-700/70">
                  {roleLabel(member.role)} · {member.status === "ativo" ? t("cfg.joined") : t("cfg.invited")}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
