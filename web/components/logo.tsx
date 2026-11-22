import { clsx } from "@/lib/format";

/** A mesma marca do site público: círculo lima com o S violeta. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="16" fill="#c6f432" />
      <path
        d="M21 9.5h-7a3.6 3.6 0 0 0 0 7.2h4a3.6 3.6 0 0 1 0 7.2H11"
        fill="none"
        stroke="#5b3df5"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="23.6" r="1.8" fill="#12101f" />
    </svg>
  );
}

export function Logo({ className, wordClassName }: { className?: string; wordClassName?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2.5", className)}>
      <LogoMark className="h-7 w-7 shrink-0" />
      <span className={clsx("font-mark text-xl font-bold leading-none tracking-[-0.03em] text-white", wordClassName)}>
        Settlr
      </span>
    </span>
  );
}
