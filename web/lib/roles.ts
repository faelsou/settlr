export const ROLE_LABEL: Record<string, string> = {
  dono: "Dono",
  financeiro: "Financeiro",
  atendente: "Atendente",
  operador: "Operador",
  agencia: "Agência",
};

export function roleLabel(role: string | undefined): string {
  if (!role) return "";
  return ROLE_LABEL[role] ?? role;
}

export function canConfigure(role: string | undefined): boolean {
  return role === "dono" || role === "operador";
}

export function canSettle(role: string | undefined): boolean {
  return role === "financeiro" || role === "dono" || role === "operador";
}
