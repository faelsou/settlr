"use client";

import { AuthButton, AuthField, AuthHeading, AuthInput, AuthNote, AuthShell, AuthTextarea } from "@/components/auth";
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
    <AuthShell
      wide
      action={
        <Link href="/login" className="auth-link">
          Já tenho conta
        </Link>
      }
      foot={<span>A conta nasce desligada e só liga com tudo no lugar.</span>}
    >
        <AuthHeading
          eyebrow="Onboarding"
          title="Criar a conta da empresa"
          sub="Política, régua, horário, WhatsApp, base legal e o atraso médio de antes da implantação nascem aqui. Sem base legal, a ativação recusa a conta."
        />

        {defaults.isError ? <AuthNote>{errorText(defaults.error)}</AuthNote> : null}
        {!draft ? <p className="auth-sub text-sm">Carregando a configuração padrão…</p> : null}

        {draft && !created ? (
          <form onSubmit={onCreate} className="grid gap-4">
            <section className="auth-card">
              <h2>Empresa</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <AuthField label="Nome">
                  <AuthInput
                    required
                    value={draft.name}
                    onChange={(event) => {
                      const name = event.target.value;
                      setDraft({ ...draft, name, slug: slugTouched ? draft.slug : slugify(name) });
                    }}
                  />
                </AuthField>
                <AuthField label="Apelido">
                  <AuthInput
                    required
                    value={draft.slug}
                    pattern="[a-z0-9-]{2,80}"
                    onChange={(event) => {
                      setSlugTouched(true);
                      setDraft({ ...draft, slug: event.target.value });
                    }}
                  />
                </AuthField>
                <AuthField label="E-mail do dono">
                  <AuthInput
                    required
                    type="email"
                    value={draft.owner_email}
                    onChange={(event) => setDraft({ ...draft, owner_email: event.target.value })}
                  />
                </AuthField>
                <AuthField label="Atraso médio antes da implantação (dias)">
                  <AuthInput
                    required
                    type="number"
                    min={0}
                    max={3650}
                    step="0.1"
                    value={draft.baseline_avg_days_late}
                    onChange={(event) => setDraft({ ...draft, baseline_avg_days_late: event.target.value })}
                  />
                </AuthField>
              </div>
              <p className="auth-sub text-sm">
                Esta linha de base fica gravada na conta. O painel compara o atraso do período com ela.
              </p>
            </section>

            <section className="auth-card">
              <h2>Política</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <AuthField label="Desconto máx. à vista (%)">
                  <AuthInput
                    value={draft.negotiation_policy.max_discount_pct_cash}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        negotiation_policy: { ...draft.negotiation_policy, max_discount_pct_cash: event.target.value },
                      })
                    }
                  />
                </AuthField>
                <AuthField label="Máx. de parcelas">
                  <AuthInput
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
                </AuthField>
              </div>
            </section>

            <section className="auth-card">
              <h2>Régua</h2>
              <p className="auth-sub text-sm">
                A conta nasce com estas etapas. O texto de cada uma continua em Configurações.
              </p>
              <ul className="flex flex-wrap gap-2">
                {draft.dunning_rules.steps.map((step) => (
                  <li key={step.key} className="auth-chip">
                    {step.key}
                  </li>
                ))}
              </ul>
            </section>

            <section className="auth-card">
              <h2>Horário</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <AuthField label="Início">
                  <AuthInput
                    type="time"
                    value={String(draft.allowed_hours.start).slice(0, 5)}
                    onChange={(event) =>
                      setDraft({ ...draft, allowed_hours: { ...draft.allowed_hours, start: event.target.value } })
                    }
                  />
                </AuthField>
                <AuthField label="Fim">
                  <AuthInput
                    type="time"
                    value={String(draft.allowed_hours.end).slice(0, 5)}
                    onChange={(event) =>
                      setDraft({ ...draft, allowed_hours: { ...draft.allowed_hours, end: event.target.value } })
                    }
                  />
                </AuthField>
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
                      aria-pressed={on}
                      className="auth-chip"
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="auth-card">
              <h2>WhatsApp e base legal</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <AuthField label="Instância">
                  <AuthInput
                    required
                    value={draft.whatsapp_instance}
                    placeholder="nome-na-evolution"
                    onChange={(event) => setDraft({ ...draft, whatsapp_instance: event.target.value })}
                  />
                </AuthField>
                <AuthField label="Número">
                  <AuthInput
                    required
                    inputMode="tel"
                    value={draft.whatsapp_number}
                    placeholder="11988887777"
                    onChange={(event) => setDraft({ ...draft, whatsapp_number: event.target.value })}
                  />
                </AuthField>
              </div>
              <AuthField label="Base legal (LGPD)">
                <AuthTextarea
                  rows={3}
                  value={draft.legal_basis}
                  placeholder="Deixe em branco para ver a ativação recusar a conta"
                  onChange={(event) => setDraft({ ...draft, legal_basis: event.target.value })}
                />
              </AuthField>
            </section>

            {error ? <AuthNote>{error}</AuthNote> : null}
            <AuthButton type="submit" disabled={busy} className="justify-self-start">
              {busy ? "Criando…" : "Criar conta"}
            </AuthButton>
          </form>
        ) : null}

        {draft && created ? (
          <section className="auth-card">
            <h2>Conta criada</h2>
            <p className="auth-sub text-sm">
              Você entrou como dono. A ativação só segue com política, régua, horário, WhatsApp e base legal.
            </p>
            {created.missing.length ? <AuthNote>Falta: {created.missing.join(", ")}</AuthNote> : null}
            {error ? <AuthNote>{error}</AuthNote> : null}
            <AuthField label="Base legal (LGPD)">
              <AuthTextarea
                rows={3}
                value={draft.legal_basis}
                onChange={(event) => setDraft({ ...draft, legal_basis: event.target.value })}
              />
            </AuthField>
            <div className="flex flex-wrap gap-2">
              <AuthButton type="button" onClick={onActivate} disabled={busy}>
                {busy ? "Ativando…" : "Ativar"}
              </AuthButton>
              <AuthButton type="button" variant="ghost" onClick={() => router.push("/configuracoes")}>
                Ir para configurações
              </AuthButton>
            </div>
          </section>
        ) : null}
    </AuthShell>
  );
}
