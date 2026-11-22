"use client";

import { AuthButton, AuthHeading, AuthNote, AuthShell } from "@/components/auth";
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
    <AuthShell
      art={{
        title: "Seu acesso, só seu.",
        lead: "O convite entra com o papel que a empresa combinou. Ninguém precisa te passar senha.",
      }}
    >
      <AuthHeading
        eyebrow="Convite"
        title="Entrar com o seu link"
        sub="Este convite é só seu. Não há senha para compartilhar e ninguém precisa te passar o login."
      />
      {error ? <AuthNote>{error}</AuthNote> : null}
      <AuthButton type="button" className="w-full" onClick={onAccept} disabled={busy || !token}>
        {busy ? "Entrando…" : "Aceitar convite"}
      </AuthButton>
      <p className="auth-sub text-[0.88rem]">
        O papel combinado aparece no painel como {roleLabel("financeiro")}, {roleLabel("atendente")} ou {roleLabel("dono")}.
      </p>
    </AuthShell>
  );
}
