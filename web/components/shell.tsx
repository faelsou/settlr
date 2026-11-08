"use client";

import { api } from "@/lib/api";
import { clearToken, supabase, supabaseEnabled } from "@/lib/auth";
import { clsx } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import {
  CheckSquare,
  CircleDollarSign,
  FileWarning,
  Gauge,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  PanelLeft,
  Send,
  Receipt,
  Search,
  Settings2,
} from "lucide-react";
import { Logo, LogoMark } from "@/components/logo";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

const NAV = [
  { href: "/inicio", label: "Início", icon: LayoutDashboard, countKey: null },
  { href: "/excecoes", label: "Exceções", icon: FileWarning, countKey: "exceptions" },
  { href: "/pagamentos", label: "Pagamentos", icon: CircleDollarSign, countKey: null },
  { href: "/titulos", label: "Títulos", icon: Receipt, countKey: null },
  { href: "/conversas", label: "Conversas", icon: MessageSquare, countKey: "conversations" },
  { href: "/entregas", label: "Entregas", icon: Send, countKey: "deliveries" },
  { href: "/aprovacoes", label: "Aprovações", icon: CheckSquare, countKey: "approvals" },
  { href: "/configuracoes", label: "Configurações", icon: Settings2, countKey: null },
  { href: "/metricas", label: "Métricas", icon: Gauge, countKey: null },
] as const;

const TITLES: Record<string, string> = {
  "/inicio": "Início",
  "/excecoes": "Exceções",
  "/pagamentos": "Pagamentos",
  "/titulos": "Títulos",
  "/conversas": "Conversas",
  "/entregas": "Entregas",
  "/aprovacoes": "Aprovações",
  "/configuracoes": "Configurações",
  "/metricas": "Métricas",
};

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  const exceptions = useQuery({
    queryKey: ["exceptions", "aberta"],
    queryFn: () => api.exceptions("aberta"),
    refetchInterval: 15000,
  });
  const approvals = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.approvals(),
    refetchInterval: 15000,
  });
  const humanChats = useQuery({
    queryKey: ["conversations", "humano"],
    queryFn: () => api.conversations("humano"),
    refetchInterval: 15000,
  });
  const failedDeliveries = useQuery({
    queryKey: ["deliveries", "falhou"],
    queryFn: () => api.deliveries(true),
    refetchInterval: 15000,
  });
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [term, setTerm] = useState("");

  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);

  useEffect(() => {
    setCollapsed(window.localStorage.getItem("cobranca.sidebar") === "1");
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const counts: Record<string, number | undefined> = {
    exceptions: exceptions.data?.total,
    approvals: approvals.data?.length,
    conversations: humanChats.data?.total,
    deliveries: failedDeliveries.data?.total,
  };
  const compact = collapsed && !mobileOpen;
  const section = Object.keys(TITLES).find((href) => pathname === href || pathname.startsWith(`${href}/`));

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem("cobranca.sidebar", next ? "1" : "0");
      return next;
    });
  }

  async function logout() {
    clearToken();
    if (supabaseEnabled()) await supabase().auth.signOut();
    router.replace("/login");
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const value = term.trim();
    router.push(value ? `/titulos?q=${encodeURIComponent(value)}` : "/titulos");
  }

  return (
    <div className="flex min-h-screen">
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Fechar menu"
          className="fixed inset-0 z-30 bg-ink-950/50 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-ink-950 text-paper-50 transition-[transform,width] duration-200 md:sticky md:top-0 md:h-screen md:translate-x-0",
          compact ? "md:w-[76px]" : "md:w-72",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className={clsx("border-b border-white/10", compact ? "px-3 py-5" : "px-6 py-6")}>
          {compact ? (
            <LogoMark className="mx-auto h-8 w-8" />
          ) : (
            <>
              <h1>
                <Logo />
              </h1>
              <p className="mt-3 truncate text-sm text-paper-200/80">{me.data?.tenant_name ?? "Carregando…"}</p>
            </>
          )}
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            const count = item.countKey ? counts[item.countKey] : undefined;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition",
                  compact && "justify-center px-0",
                  active ? "bg-brand-700 text-white" : "text-paper-200/80 hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon size={18} />
                {compact ? null : <span className="flex-1 font-medium">{item.label}</span>}
                {count ? (
                  compact ? (
                    <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-signal-400" />
                  ) : (
                    <span className="rounded-full bg-signal-400 px-2 py-0.5 text-[11px] font-bold text-ink-950">{count}</span>
                  )
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className={clsx("border-t border-white/10", compact ? "px-3 py-4" : "px-5 py-4")}>
          {compact ? (
            <p className="mb-3 grid h-9 w-9 place-items-center rounded-full bg-white/10 text-sm font-semibold" title={me.data?.email}>
              {(me.data?.email ?? "?").slice(0, 1).toUpperCase()}
            </p>
          ) : (
            <>
              <p className="truncate text-sm text-paper-50">{me.data?.email}</p>
              <p className="text-xs capitalize text-paper-200/70">{me.data?.role}</p>
            </>
          )}
          <button
            type="button"
            onClick={logout}
            title="Sair"
            className={clsx(
              "inline-flex items-center gap-2 text-sm text-paper-200/80 hover:text-white",
              compact ? "justify-center" : "mt-3",
            )}
          >
            <LogOut size={16} />
            {compact ? null : "Sair"}
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-paper-200 bg-white/80 px-4 py-3 backdrop-blur md:px-8">
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-full text-ink-800 hover:bg-paper-100 md:hidden"
            aria-label="Abrir menu"
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={18} />
          </button>
          <button
            type="button"
            className="hidden h-9 w-9 place-items-center rounded-full text-ink-800 hover:bg-paper-100 md:grid"
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            onClick={toggleCollapsed}
          >
            <PanelLeft size={18} />
          </button>
          <p className="hidden text-sm font-semibold text-ink-900 sm:block">{section ? TITLES[section] : "Painel"}</p>
          <form onSubmit={onSearch} className="relative ml-auto min-w-0 w-full max-w-md">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-700/40" />
            <input
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Buscar devedor, documento ou referência"
              aria-label="Buscar títulos"
              className="w-full rounded-full border border-paper-200 bg-paper-50 py-2 pl-9 pr-3 text-sm text-ink-900 outline-none ring-brand-600/30 focus:border-brand-700 focus:ring-2"
            />
          </form>
        </header>
        <main className="flex min-h-0 flex-1 flex-col px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}
