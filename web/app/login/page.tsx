"use client";

import { Logo } from "@/components/logo";
import { Banner, Button, Field, Input } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { setToken, supabase, supabaseEnabled } from "@/lib/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("operador@demo.local");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hasSupabase = supabaseEnabled();

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
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_0.9fr]">
      <section className="hidden flex-col justify-between bg-brand-700 px-12 py-16 text-white lg:flex">
        <div>
          <Logo wordClassName="text-3xl" />
          <h1 className="mt-10 max-w-md font-display text-5xl leading-tight">Cobrou, recebeu, conciliou.</h1>
        </div>
        <p className="max-w-sm text-sm leading-relaxed text-white/80">
          Exceções, pagamentos e o WhatsApp do devedor. Confirmar uma baixa continua passando pela API.
        </p>
      </section>
      <section className="grid place-items-center bg-paper-50 px-4 py-16">
      <div className="w-full max-w-md rounded-3xl border border-paper-200 bg-white p-8 shadow-card">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-brand-700">Painel do operador</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Entrar</h1>
        <p className="mt-2 text-sm text-ink-700/70">
          {hasSupabase
            ? "Use a conta do tenant no Supabase Auth. O JWT carrega o tenant_id."
            : "Ambiente local: o token é emitido pela API após o seed-demo."}
        </p>
        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <Field label="E-mail">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          {hasSupabase ? (
            <Field label="Senha">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </Field>
          ) : (
            <Field label="Tenant">
              <Input value={slug} onChange={(e) => setSlug(e.target.value)} required />
            </Field>
          )}
          {error ? <Banner>{error}</Banner> : null}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Entrando…" : "Entrar"}
          </Button>
        </form>
        <p className="mt-6 text-sm text-ink-700/70">
          Primeira vez na empresa?{" "}
          <Link href="/comecar" className="font-semibold text-brand-700">
            Criar a conta
          </Link>
        </p>
      </div>
      </section>
    </main>
  );
}
