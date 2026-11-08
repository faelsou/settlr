"use client";

import { Logo } from "@/components/logo";
import { Banner, Button } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { roleLabel } from "@/lib/roles";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

export default function ConvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const token = decodeURIComponent(params.token ?? "");

  async function onAccept() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.acceptInvite(token);
      setToken(result.access_token);
      router.replace("/inicio");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-paper-50 px-4 py-16">
      <div className="w-full max-w-md space-y-6 rounded-3xl border border-paper-200 bg-white p-8 shadow-card">
        <Logo />
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-brand-700">Convite</p>
          <h1 className="mt-2 font-display text-3xl text-ink-900">Entrar com o seu link</h1>
          <p className="mt-2 text-sm text-ink-700/70">
            Este convite é só seu. Não há senha para compartilhar e ninguém precisa te passar o login.
          </p>
        </div>
        {error ? <Banner>{error}</Banner> : null}
        <Button type="button" className="w-full" onClick={onAccept} disabled={busy || !token}>
          {busy ? "Entrando…" : "Aceitar convite"}
        </Button>
        <p className="text-xs text-ink-700/60">O papel combinado aparece no painel como {roleLabel("financeiro")}, {roleLabel("atendente")} ou {roleLabel("dono")}.</p>
      </div>
    </main>
  );
}
