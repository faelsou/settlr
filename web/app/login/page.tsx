"use client";

import { AuthButton, AuthField, AuthHeading, AuthInput, AuthNote, AuthShell } from "@/components/auth";
import { api, errorText } from "@/lib/api";
import { setToken, supabase, supabaseEnabled } from "@/lib/auth";
import { isLang, useI18n } from "@/lib/i18n";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Sessão entregue pelo site público (/entrar): #access_token=…&refresh_token=…&lang=….
 * O fragmento não vai ao servidor; aqui ele é lido e apagado da barra antes de qualquer outra coisa.
 */
function takeHandoff(): { access: string; refresh: string | null; lang: string | null } | null {
  if (typeof window === "undefined" || !window.location.hash.includes("access_token=")) return null;
  const params = new URLSearchParams(window.location.hash.slice(1));
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  const access = params.get("access_token");
  return access ? { access, refresh: params.get("refresh_token"), lang: params.get("lang") } : null;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("operador@demo.local");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hasSupabase = supabaseEnabled();
  const { t, setLang } = useI18n();

  useEffect(() => {
    const handoff = takeHandoff();
    if (!handoff) return;
    // O idioma escolhido no site vale no painel, que mora em outra origem.
    if (isLang(handoff.lang)) setLang(handoff.lang);
    setBusy(true);
    (async () => {
      try {
        // Com refresh token, a sessão do Supabase se renova sozinha no painel.
        if (hasSupabase && handoff.refresh) {
          const { error: sessionError } = await supabase().auth.setSession({
            access_token: handoff.access,
            refresh_token: handoff.refresh,
          });
          if (sessionError) throw sessionError;
        }
        setToken(handoff.access);
        router.replace("/inicio");
      } catch (err) {
        setError(errorText(err));
        setBusy(false);
      }
    })();
  }, [hasSupabase, router, setLang]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (hasSupabase) {
        const { data, error: authError } = await supabase().auth.signInWithPassword({ email, password });
        if (authError || !data.session) throw new Error(authError?.message ?? t("login.fail"));
        setToken(data.session.access_token);
      } else {
        const result = await api.devLogin(email, slug);
        setToken(result.access_token);
      }
      router.replace("/inicio");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      foot={
        <>
          {hasSupabase ? null : <span>{t("login.dev")}</span>}
          <span>{t("auth.help")}</span>
        </>
      }
    >
      <AuthHeading eyebrow={t("login.eyebrow")} title={t("login.title")} sub={t("login.sub")} />
      <form onSubmit={onSubmit} className="auth-form">
        <AuthField label={t("login.email")}>
          <AuthInput
            type="email"
            autoComplete="username"
            inputMode="email"
            placeholder={t("login.emailPh")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </AuthField>
        {hasSupabase ? (
          <AuthField label={t("login.password")}>
            <AuthInput
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </AuthField>
        ) : (
          <AuthField label={t("login.company")}>
            <AuthInput
              autoComplete="organization"
              spellCheck={false}
              placeholder="demo"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              required
            />
          </AuthField>
        )}
        {error ? <AuthNote>{error}</AuthNote> : null}
        <AuthButton type="submit" disabled={busy} className="w-full">
          {busy ? t("login.busy") : t("login.submit")}
        </AuthButton>
      </form>
      <p className="auth-sub text-[0.88rem]">
        {t("login.invite")}
      </p>
      <div className="auth-divider">{t("login.divider")}</div>
      <Link href="/comecar" className="auth-btn auth-btn-ghost w-full">
        {t("login.create")}
      </Link>
    </AuthShell>
  );
}
