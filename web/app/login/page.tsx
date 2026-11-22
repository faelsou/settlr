"use client";

import { AuthButton, AuthField, AuthHeading, AuthInput, AuthNote, AuthShell } from "@/components/auth";
import { api, errorText } from "@/lib/api";
import { setToken, supabase, supabaseEnabled } from "@/lib/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Sessão entregue pelo site público (/entrar): #access_token=…&refresh_token=….
 * O fragmento não vai ao servidor; aqui ele é lido e apagado da barra antes de qualquer outra coisa.
 */
function takeHandoff(): { access: string; refresh: string | null } | null {
  if (typeof window === "undefined" || !window.location.hash.includes("access_token=")) return null;
  const params = new URLSearchParams(window.location.hash.slice(1));
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  const access = params.get("access_token");
  return access ? { access, refresh: params.get("refresh_token") } : null;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("operador@demo.local");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hasSupabase = supabaseEnabled();

  useEffect(() => {
    const handoff = takeHandoff();
    if (!handoff) return;
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
  }, [hasSupabase, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (hasSupabase) {
        const { data, error: authError } = await supabase().auth.signInWithPassword({ email, password });
        if (authError || !data.session) throw new Error(authError?.message ?? "Falha no login");
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
          {hasSupabase ? null : <span>ambiente local · entrada sem senha</span>}
          <span>Problema para entrar? Fale com o dono da conta da sua empresa.</span>
        </>
      }
    >
      <AuthHeading eyebrow="Área do cliente" title="Entrar no painel" sub="Exceções, pagamentos e conversas da sua empresa." />
      <form onSubmit={onSubmit} className="auth-form">
        <AuthField label="E-mail">
          <AuthInput
            type="email"
            autoComplete="username"
            inputMode="email"
            placeholder="voce@empresa.com.br"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </AuthField>
        {hasSupabase ? (
          <AuthField label="Senha">
            <AuthInput
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </AuthField>
        ) : (
          <AuthField label="Empresa">
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
          {busy ? "Entrando…" : "Entrar"}
        </AuthButton>
      </form>
      <p className="auth-sub text-[0.88rem]">
        Recebeu um convite da sua empresa? Abra o link do e-mail para entrar com o seu acesso.
      </p>
      <div className="auth-divider">Primeira vez na empresa</div>
      <Link href="/comecar" className="auth-btn auth-btn-ghost w-full">
        Criar a conta da empresa
      </Link>
    </AuthShell>
  );
}
