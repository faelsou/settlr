"use client";

import { AuthButton, AuthHeading, AuthNote, AuthShell } from "@/components/auth";
import { api, errorText } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

export default function ConvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const token = decodeURIComponent(params.token ?? "");
  const { t } = useI18n();

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
        title: t("invite.artTitle"),
        lead: t("invite.artLead"),
      }}
    >
      <AuthHeading
        eyebrow={t("invite.eyebrow")}
        title={t("invite.title")}
        sub={t("invite.sub")}
      />
      {error ? <AuthNote>{error}</AuthNote> : null}
      <AuthButton type="button" className="w-full" onClick={onAccept} disabled={busy || !token}>
        {busy ? t("login.busy") : t("invite.accept")}
      </AuthButton>
      <p className="auth-sub text-[0.88rem]">
        {t("invite.roles", { a: roleLabel("financeiro"), b: roleLabel("atendente"), c: roleLabel("dono") })}
      </p>
    </AuthShell>
  );
}
