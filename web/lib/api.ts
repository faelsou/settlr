import { apiBase, clearToken, resolveAccessToken } from "./auth";
import type {
  Approval,
  Conversation,
  Debtor,
  Delivery,
  Invoice,
  InvoiceDetail,
  Me,
  Message,
  Metrics,
  Page,
  Payment,
  ReviewException,
  TenantSettings,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Erro ${status}`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await resolveAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    const raw = await res.text();
    let detail: unknown = raw || res.statusText;
    try {
      const body = JSON.parse(raw) as { detail?: unknown };
      detail = body.detail ?? body;
    } catch {
      detail = raw || res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  me: () => request<Me>("/me"),
  devLogin: (email: string, tenantSlug: string) =>
    request<{ access_token: string; tenant_name: string; email: string; role: string }>(
      "/auth/dev-login",
      { method: "POST", body: JSON.stringify({ email, tenant_slug: tenantSlug }) },
    ),

  exceptions: (status = "aberta") =>
    request<Page<ReviewException>>(`/exceptions?status=${status}&limit=100`),
  confirmException: (id: string, body: Record<string, unknown>) =>
    request<ReviewException>(`/exceptions/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rejectException: (id: string, body: Record<string, unknown>) =>
    request<ReviewException>(`/exceptions/${id}/reject`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  payments: (params: { status?: string; origin?: string } = {}) => {
    const q = new URLSearchParams({ limit: "100" });
    if (params.status) q.set("status", params.status);
    if (params.origin) q.set("origin", params.origin);
    return request<Page<Payment>>(`/payments?${q}`);
  },
  importStatement: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ created: number; duplicates: number }>(`/payments/import`, {
      method: "POST",
      body: data,
    });
  },
  exportSettlements: async (start: string, end: string) => {
    const token = await resolveAccessToken();
    const query = new URLSearchParams({ start, end });
    const res = await fetch(`${apiBase()}/payments/export?${query}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.status === 401) {
      clearToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    if (!res.ok) {
      const raw = await res.text();
      let detail: unknown = raw || res.statusText;
      try {
        const body = JSON.parse(raw) as { detail?: unknown };
        detail = body.detail ?? body;
      } catch {
        detail = raw || res.statusText;
      }
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const header = res.headers.get("Content-Disposition") ?? "";
    const name = header.match(/filename="([^"]+)"/)?.[1] ?? `baixas-${start}-${end}.csv`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
  receiptUrl: async (paymentId: string) => {
    const token = await resolveAccessToken();
    const res = await fetch(`${apiBase()}/payments/${paymentId}/receipt`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new ApiError(res.status, "comprovante indisponível");
    return URL.createObjectURL(await res.blob());
  },
  exceptionFile: async (exceptionId: string) => {
    const token = await resolveAccessToken();
    const res = await fetch(`${apiBase()}/exceptions/${exceptionId}/file`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new ApiError(res.status, "comprovante indisponível");
    return res.blob();
  },

  invoices: (params: { status?: string; q?: string; semPagamento?: boolean } = {}) => {
    const query = new URLSearchParams({ limit: "100" });
    if (params.status) query.set("status", params.status);
    if (params.q) query.set("q", params.q);
    if (params.semPagamento) query.set("sem_pagamento", "true");
    return request<Page<Invoice>>(`/invoices?${query}`);
  },
  invoice: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  saveWhatsappNumbers: (debtorId: string, phones: string[]) =>
    request<Debtor>(`/debtors/${debtorId}/whatsapp`, {
      method: "PATCH",
      body: JSON.stringify({ phones }),
    }),
  importInvoices: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<{ created: number; updated: number }>(`/invoices/import`, {
      method: "POST",
      body: data,
    });
  },

  conversations: (state?: string) => {
    const q = new URLSearchParams({ limit: "100" });
    if (state) q.set("state", state);
    return request<Page<Conversation>>(`/conversations?${q}`);
  },
  deliveries: (failed = false) => {
    const q = new URLSearchParams({ limit: "100" });
    if (failed) q.set("falhou", "true");
    return request<Page<Delivery>>(`/conversations/deliveries?${q}`);
  },
  messages: (id: string) => request<Message[]>(`/conversations/${id}/messages`),
  takeover: (id: string) =>
    request<Conversation>(`/conversations/${id}/takeover`, { method: "POST" }),
  release: (id: string) =>
    request<Conversation>(`/conversations/${id}/release`, { method: "POST" }),
  sendMessage: (id: string, text: string) =>
    request<Message>(`/conversations/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  approvals: (status = "pendente") => request<Approval[]>(`/approvals?status=${status}`),
  decideApproval: (id: string, approved: boolean, message: string) =>
    request<{ status: string }>(`/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ approved, message }),
    }),

  settings: () => request<TenantSettings>("/settings"),
  saveSettings: (body: TenantSettings) =>
    request<TenantSettings>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  saveWhatsappSenders: (senders: { instance: string; number: string }[]) =>
    request<{ instance: string; number: string }[]>("/settings/whatsapp", {
      method: "PUT",
      body: JSON.stringify({ senders }),
    }),

  metrics: (start?: string, end?: string) => {
    const q = new URLSearchParams();
    if (start) q.set("start", start);
    if (end) q.set("end", end);
    const suffix = q.toString() ? `?${q}` : "";
    return request<Metrics>(`/metrics${suffix}`);
  },
};

export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (Array.isArray(err.detail)) {
      return err.detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : JSON.stringify(item)))
        .join(" · ");
    }
    if (typeof err.detail === "object" && err.detail && "missing" in err.detail) {
      return `Falta: ${(err.detail as { missing: string[] }).missing.join(", ")}`;
    }
    return JSON.stringify(err.detail);
  }
  if (err instanceof Error && err.message === "Failed to fetch") return "Não foi possível falar com a API.";
  return err instanceof Error ? err.message : "Erro inesperado";
}
