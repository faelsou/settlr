import { tr } from "@/lib/i18n";
import { MESSAGES, type MessageKey } from "@/lib/messages";

/** Nome do papel no idioma do painel. Chame dentro de um componente que usa useI18n(). */
export function roleLabel(role: string | undefined): string {
  if (!role) return "";
  const key = `role.${role}`;
  return key in MESSAGES ? tr(key as MessageKey) : role;
}

export function canConfigure(role: string | undefined): boolean {
  // Espelha CONFIGURE_ROLES de api/app/core/roles.py (SETL-69).
  return role === "dono";
}

export function canSettle(role: string | undefined): boolean {
  return role === "financeiro" || role === "dono" || role === "operador";
}
