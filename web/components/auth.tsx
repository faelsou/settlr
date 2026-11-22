"use client";

/*
 * Entrada do painel (login, comecar, convite) com o mesmo visual do /entrar do site público.
 * As classes `auth-*` estão em app/globals.css e espelham site/public/entrar/index.html.
 */

import { Logo } from "@/components/logo";
import { clsx } from "@/lib/format";
import Link from "next/link";
import { useEffect, useRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

function Aurora() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const blobs = [
      { c: "rgba(91,61,245,.9)", r: 0.5, x: 0.35, y: 0.3, sx: 0.00019, sy: 0.00015 },
      { c: "rgba(143,120,255,.55)", r: 0.35, x: 0.75, y: 0.2, sx: 0.00015, sy: 0.00021 },
      { c: "rgba(198,244,50,.18)", r: 0.25, x: 0.6, y: 0.7, sx: 0.00023, sy: 0.00012 },
    ];
    let frame = 0;
    const size = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, rect.width / 3);
      canvas.height = Math.max(1, rect.height / 3);
    };
    const draw = (tm: number) => {
      const { width: w, height: h } = canvas;
      ctx.clearRect(0, 0, w, h);
      blobs.forEach((b, i) => {
        const x = (b.x + Math.sin(tm * b.sx + i) * 0.08) * w;
        const y = (b.y + Math.cos(tm * b.sy + i * 2) * 0.07) * h;
        const r = b.r * Math.max(w, h);
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, b.c);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      });
      if (!reduce) frame = requestAnimationFrame(draw);
    };
    size();
    window.addEventListener("resize", size);
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", size);
    };
  }, []);

  return <canvas ref={ref} />;
}

const brl = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

/** Lado direito: a fila do dia em cartões, o que o operador encontra ao entrar. */
function AuthArt({ title, lead }: { title: string; lead: string }) {
  return (
    <aside className="auth-art" aria-hidden="true">
      <Aurora />
      <div className="auth-grid" />
      <div>
        <h2>{title}</h2>
        <p className="auth-lead">{lead}</p>
      </div>
      <div className="auth-cards">
        <div className="auth-float">
          <div className="top">
            <b>PIX · Marina Souza</b>
            <span className="v">{brl(480)}</span>
          </div>
          <div className="top">
            <small>E2E igual ao do título</small>
            <span className="auth-tag ok">conciliado</span>
          </div>
        </div>
        <div className="auth-float">
          <div className="top">
            <b>PIX · F. Almeida</b>
            <span className="v">{brl(520)}</span>
          </div>
          <div className="top">
            <small>2 títulos possíveis</small>
            <span className="auth-tag wait">para confirmar</span>
          </div>
        </div>
        <div className="auth-float">
          <div className="top">
            <b>Pedido de 8 parcelas</b>
            <span className="v">{brl(1150)}</span>
          </div>
          <div className="top">
            <small>acima do teto de 6</small>
            <span className="auth-tag vi">aprovação</span>
          </div>
        </div>
      </div>
      <div className="auth-art-foot">
        <span>Dados de exemplo</span>
        <span>PIX · boleto · Open Finance</span>
      </div>
    </aside>
  );
}

export function AuthShell({
  children,
  action,
  foot,
  wide = false,
  art = { title: "Cobrou, recebeu, conciliou.", lead: "Ao entrar, você vê só o que precisa de uma decisão. O resto o sistema já baixou com o banco." },
}: {
  children: ReactNode;
  /** Link no canto superior direito (ex.: "Já tenho conta"). */
  action?: ReactNode;
  foot?: ReactNode;
  /** Formulário largo, sem o lado da arte (comecar). */
  wide?: boolean;
  art?: { title: string; lead: string };
}) {
  return (
    <main className={clsx("auth", wide && "auth-wide")}>
      <div className="auth-split">
        <section className="auth-side">
          <div className="auth-bar">
            <Link href="/login" className="no-underline" aria-label="Settlr">
              <Logo />
            </Link>
            {action}
          </div>
          <div className="auth-box">{children}</div>
          <div className="auth-foot">{foot ?? <span>Problema para entrar? Fale com o dono da conta da sua empresa.</span>}</div>
        </section>
        {wide ? null : <AuthArt {...art} />}
      </div>
    </main>
  );
}

export function AuthHeading({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: ReactNode }) {
  return (
    <div className="grid gap-3">
      <span className="auth-eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      {sub ? <p className="auth-sub">{sub}</p> : null}
    </div>
  );
}

export function AuthField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="auth-field">
      <span className="auth-label">{label}</span>
      {children}
    </label>
  );
}

export function AuthInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx("auth-ctl", className)} />;
}

export function AuthTextarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx("auth-ctl", className)} />;
}

export function AuthButton({
  variant = "light",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "light" | "ghost" }) {
  return <button {...props} className={clsx("auth-btn", variant === "light" ? "auth-btn-light" : "auth-btn-ghost", className)} />;
}

export function AuthNote({ children, tone = "bad" }: { children: ReactNode; tone?: "bad" | "ok" | "info" }) {
  return (
    <p role={tone === "bad" ? "alert" : undefined} className={clsx("auth-note", tone !== "info" && tone)}>
      {children}
    </p>
  );
}
