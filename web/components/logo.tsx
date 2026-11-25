import { clsx } from "@/lib/format";

/**
 * Símbolo Kitou (manual Pulso): círculo cheio com o check de pontas arredondadas, traço de 11% do diâmetro.
 * Por padrão, círculo Limão e check Tinta. `inverse` troca para círculo Tinta e check Limão.
 */
export function LogoMark({ className, inverse = false }: { className?: string; inverse?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="16" fill={inverse ? "#0E0F1A" : "#C6F432"} />
      <path
        d="M9.6 16.6 L14.1 21 L22.6 11.4"
        fill="none"
        stroke={inverse ? "#C6F432" : "#0E0F1A"}
        strokeWidth="3.52"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Logo horizontal: símbolo + "kitou" em Space Grotesk Bold, sempre em minúsculas. Branco por padrão (fundo Tinta). */
export function Logo({ className, wordClassName }: { className?: string; wordClassName?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2", className)}>
      <LogoMark className="h-7 w-7 shrink-0" />
      <span className={clsx("font-mark text-[1.55rem] font-bold leading-none tracking-[-0.02em] text-white", wordClassName)}>
        kitou
      </span>
    </span>
  );
}
