"use client";

import { Logo } from "@/components/logo";
import { Banner, Button, Field, Input, Textarea } from "@/components/ui";
import { ApiError, api, errorText } from "@/lib/api";
import { setToken } from "@/lib/auth";
import type { TenantSettings } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

type Draft = {
  name: string;
  slug: string;
  owner_email: string;
  baseline_avg_days_late: string;
  whatsapp_instance: string;
  whatsapp_number: string;
  legal_basis: string;
  timezone: string;
  negotiation_policy: TenantSettings["negotiation_policy"];
  dunning_rules: TenantSettings["dunning_rules"];
  allowed_hours: TenantSettings["allowed_hours"];
};

function missingOf(err: unknown): string[] | null {
  if (!(err instanceof ApiError) || !err.detail || typeof err.detail !== "object") return null;
  if (!("missing" in err.detail)) return null;
  const missing = (err.detail as { missing?: unknown }).missing;
  return Array.isArray(missing) ? missing.map(String) : null;
}

function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

export default function ComecarPage() {
  const router = useRouter();
  const defaults = useQuery({ queryKey: ["onboarding-defaults"], queryFn: api.onboardingDefaults });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [slugTouched, setSlugTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ missing: string[] } | null>(null);

  useEffect(() => {
    if (!defaults.data || draft) return;
    setDraft({
      name: "",
      slug: "",
      owner_email: "",
      baseline_avg_days_late: "",
      whatsapp_instance: "",
      whatsapp_number: "",
      legal_basis: "",
      timezone: defaults.data.timezone,
      negotiation_policy: defaults.data.negotiation_policy,
      dunning_rules: defaults.data.dunning_rules,
      allowed_hours: defaults.data.allowed_hours,
    });
  }, [defaults.data, draft]);

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createCompany({
        ...draft,
        legal_basis: draft.legal_basis.trim() || null,
        whatsapp_instance: draft.whatsapp_instance.trim(),
        whatsapp_number: draft.whatsapp_number.trim(),
        baseline_avg_days_late: Number(draft.baseline_avg_days_late),
      });
      setToken(result.access_token);
      setCreated({ missing: result.missing });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function onActivate() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const current = await api.settings();
      const saved = await api.saveSettings({ ...current, legal_basis: draft.legal_basis.trim() });
      const active = await api.activate();
      setCreated({ missing: active.missing ?? saved.missing ?? [] });
      if (active.active) router.push("/inicio");
    } catch (err) {
      const missing = missingOf(err);
      if (missing) setCreated({ missing });
      else setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-paper-50 px-4 py-10">
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <div className="flex items-center justify-between">
          <Logo />
          <Link href="/login" className="text-sm font-semibold text-brand-700">
            Já tenho conta
          </Link>
        </div>
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-brand-700">Onboarding</p>
          <h1 className="mt-2 font-display text-4xl text-ink-900">Criar a conta da empresa</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-700/70">
            Política, régua, horário, WhatsApp, base legal e o atraso médio de antes da implantação nascem aqui.
            Sem base legal, a ativação recusa a conta.
          </p>
        </div>

        {defaults.isError ? <Banner>{errorText(defaults.error)}</Banner> : null}
        {!draft ? <p className="text-sm text-ink-700/70">Carregando a configuração padrão…</p> : null}

        {draft && !created ? (
          <form onSubmit={onCreate} className="space-y-6">
            <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
              <h2 className="font-display text-2xl">Empresa</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Nome">
                  <Input
                    required
                    value={draft.name}
                    onChange={(event) => {
                      const name = event.target.value;
                      setDraft({ ...draft, name, slug: slugTouched ? draft.slug : slugify(name) });
                    }}
                  />
                </Field>
                <Field label="Apelido">
                  <Input
                    required
                    value={draft.slug}
                    pattern="[a-z0-9-]{2,80}"
                    onChange={(event) => {
                      setSlugTouched(true);
                      setDraft({ ...draft, slug: event.target.value });
                    }}
                  />
                </Field>
                <Field label="E-mail do dono">
                  <Input
                    required
                    type="email"
                    value={draft.owner_email}
                    onChange={(event) => setDraft({ ...draft, owner_email: event.target.value })}
                  />
                </Field>
                <Field label="Atraso médio antes da implantação (dias)">
                  <Input
                    required
                    type="number"
                    min={0}
                    max={3650}
                    step="0.1"
                    value={draft.baseline_avg_days_late}
                    onChange={(event) => setDraft({ ...draft, baseline_avg_days_late: event.target.value })}
                  />
                </Field>
              </div>
              <p className="text-sm text-ink-700/70">
                Esta linha de base fica gravada na conta. O painel compara o atraso do período com ela.
              </p>
            </section>

            <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
              <h2 className="font-display text-2xl">Política</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Desconto máx. à vista (%)">
                  <Input
                    value={draft.negotiation_policy.max_discount_pct_cash}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        negotiation_policy: { ...draft.negotiation_policy, max_discount_pct_cash: event.target.value },
                      })
                    }
                  />
                </Field>
                <Field label="Máx. de parcelas">
                  <Input
                    type="number"
                    value={draft.negotiation_policy.max_installments}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        negotiation_policy: {
                          ...draft.negotiation_policy,
                          max_installments: Number(event.target.value),
                        },
                      })
                    }
                  />
                </Field>
              </div>
            </section>

            <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
              <h2 className="font-display text-2xl">Régua</h2>
              <p className="text-sm text-ink-700/70">
                A conta nasce com estas etapas. O texto de cada uma continua em Configurações.
              </p>
              <ul className="flex flex-wrap gap-2">
                {draft.dunning_rules.steps.map((step) => (
                  <li key={step.key} className="rounded-full bg-paper-100 px-3 py-1 text-sm">
                    {step.key}
                  </li>
                ))}
              </ul>
            </section>

            <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
              <h2 className="font-display text-2xl">Horário</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Início">
                  <Input
                    type="time"
                    value={String(draft.allowed_hours.start).slice(0, 5)}
                    onChange={(event) =>
                      setDraft({ ...draft, allowed_hours: { ...draft.allowed_hours, start: event.target.value } })
                    }
                  />
                </Field>
                <Field label="Fim">
                  <Input
                    type="time"
                    value={String(draft.allowed_hours.end).slice(0, 5)}
                    onChange={(event) =>
                      setDraft({ ...draft, allowed_hours: { ...draft.allowed_hours, end: event.target.value } })
                    }
                  />
                </Field>
              </div>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map((label, index) => {
                  const on = draft.allowed_hours.weekdays.includes(index);
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => {
                        const weekdays = on
                          ? draft.allowed_hours.weekdays.filter((day) => day !== index)
                          : [...draft.allowed_hours.weekdays, index].sort();
                        setDraft({ ...draft, allowed_hours: { ...draft.allowed_hours, weekdays } });
                      }}
                      className={`rounded-full px-3 py-1 text-sm ${on ? "bg-brand-700 text-white" : "bg-paper-100 text-ink-800"}`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
              <h2 className="font-display text-2xl">WhatsApp e base legal</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Instância">
                  <Input
                    required
                    value={draft.whatsapp_instance}
                    placeholder="nome-na-evolution"
                    onChange={(event) => setDraft({ ...draft, whatsapp_instance: event.target.value })}
                  />
                </Field>
                <Field label="Número">
                  <Input
                    required
                    inputMode="tel"
                    value={draft.whatsapp_number}
                    placeholder="11988887777"
                    onChange={(event) => setDraft({ ...draft, whatsapp_number: event.target.value })}
                  />
                </Field>
              </div>
              <Field label="Base legal (LGPD)">
                <Textarea
                  rows={3}
                  value={draft.legal_basis}
                  placeholder="Deixe em branco para ver a ativação recusar a conta"
                  onChange={(event) => setDraft({ ...draft, legal_basis: event.target.value })}
                />
              </Field>
            </section>

            {error ? <Banner>{error}</Banner> : null}
            <Button type="submit" disabled={busy}>
              {busy ? "Criando…" : "Criar conta"}
            </Button>
          </form>
        ) : null}

        {draft && created ? (
          <section className="space-y-4 rounded-3xl border border-paper-200 bg-white p-6 shadow-card">
            <h2 className="font-display text-2xl">Conta criada</h2>
            <p className="text-sm text-ink-700/70">
              Você entrou como dono. A ativação só segue com política, régua, horário, WhatsApp e base legal.
            </p>
            {created.missing.length ? <Banner>Falta: {created.missing.join(", ")}</Banner> : null}
            {error ? <Banner>{error}</Banner> : null}
            <Field label="Base legal (LGPD)">
              <Textarea
                rows={3}
                value={draft.legal_basis}
                onChange={(event) => setDraft({ ...draft, legal_basis: event.target.value })}
              />
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button type="button" onClick={onActivate} disabled={busy}>
                {busy ? "Ativando…" : "Ativar"}
              </Button>
              <Button type="button" variant="outline" onClick={() => router.push("/configuracoes")}>
                Ir para configurações
              </Button>
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
