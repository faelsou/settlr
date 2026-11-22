import { clsx } from "@/lib/format";
import { Upload } from "lucide-react";
import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("rounded-2xl border border-paper-200 bg-white shadow-card", className)}>{children}</section>;
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "outline" }) {
  const styles = {
    primary: "bg-brand-700 text-white hover:bg-brand-600 disabled:bg-ink-700/30",
    ghost: "bg-transparent text-ink-800 hover:bg-paper-100",
    danger: "bg-red-700 text-white hover:bg-red-600",
    outline: "border border-paper-200 bg-white text-ink-800 hover:border-brand-600",
  }[variant];
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed",
        styles,
        className,
      )}
      {...props}
    />
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none ring-brand-600/30 focus:border-brand-700 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={clsx(
        "w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm text-ink-900 outline-none ring-brand-600/30 focus:border-brand-700 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-mono font-medium uppercase tracking-[0.04em] text-ink-700/70">{children}</label>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-6 py-16 text-center">
      <p className="font-display text-xl text-ink-900">{title}</p>
      {hint ? <p className="mt-2 text-sm text-ink-700/70">{hint}</p> : null}
    </div>
  );
}

export function Banner({ children, tone = "error" }: { children: ReactNode; tone?: "error" | "ok" }) {
  return (
    <p
      className={clsx(
        "rounded-xl px-3 py-2 text-sm",
        tone === "error" ? "bg-red-50 text-red-800" : "bg-signal-100 text-ink-950",
      )}
    >
      {children}
    </p>
  );
}

export function PageHeader({
  eyebrow,
  title,
  hint,
  actions,
}: {
  eyebrow?: string;
  title: string;
  hint?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow ? <p className="text-xs font-mono uppercase tracking-[0.04em] text-brand-700">{eyebrow}</p> : null}
        <h1 className="font-display text-3xl tracking-tight">{title}</h1>
        {hint ? <p className="mt-1 max-w-2xl text-sm text-ink-700/70">{hint}</p> : null}
      </div>
      {actions}
    </header>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex max-w-full gap-1 overflow-x-auto rounded-full border border-paper-200 bg-white p-1"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={clsx(
              "shrink-0 rounded-full px-3 py-1.5 text-sm font-semibold transition",
              active ? "bg-ink-950 text-white shadow-sm" : "text-ink-700 hover:bg-paper-100",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-xl bg-paper-200/70", className)} />;
}

export function Breadcrumb({ items }: { items: { href?: string; label: string }[] }) {
  return (
    <nav aria-label="Trilha" className="flex flex-wrap items-center gap-2 text-sm text-ink-700/70">
      {items.map((item, index) => (
        <span key={`${item.label}-${index}`} className="flex items-center gap-2">
          {index > 0 ? <span aria-hidden="true">/</span> : null}
          {item.href ? (
            <Link href={item.href} className="font-semibold text-brand-700 no-underline hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink-900">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function Dialog({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink-950/50 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        className="w-full max-w-md rounded-3xl border border-paper-200 bg-white p-6 shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="dialog-title" className="font-display text-2xl">
          {title}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-700/80">{body}</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="button" variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={busy}>
            {busy ? "Salvando…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function FileButton({
  label,
  accept,
  onFile,
}: {
  label: string;
  accept: string;
  onFile: (file: File) => void;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-paper-200 bg-white px-4 py-2 text-sm font-semibold text-ink-800 transition hover:border-brand-600">
      <Upload size={16} className="text-brand-700" />
      {label}
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </label>
  );
}
