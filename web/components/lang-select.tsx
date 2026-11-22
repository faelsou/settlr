"use client";

/* Seletor de idioma com o mesmo desenho do site público. Feito para fundo escuro (entrada e menu lateral). */

import { LANG_INFO, LANGS, useI18n } from "@/lib/i18n";
import { clsx } from "@/lib/format";
import { ChevronDown, Globe } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function LangSelect({ compact = false, up = false }: { compact?: boolean; up?: boolean }) {
  const { lang, setLang, t } = useI18n();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const info = LANG_INFO[lang];

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("lang.aria", { name: `${info.name} (${info.region})` })}
        onClick={() => setOpen((value) => !value)}
        className={clsx(
          "inline-flex h-9 items-center gap-2 rounded-full border border-white/15 px-3 font-mono text-[0.76rem] text-night-fg transition hover:border-brand-500/50 hover:bg-white/5",
          open && "border-brand-500/50 bg-white/5",
          compact && "w-9 justify-center px-0",
        )}
      >
        <Globe size={15} />
        {compact ? null : (
          <>
            <span>{info.code}</span>
            <ChevronDown size={12} className={clsx("transition", open && "rotate-180")} />
          </>
        )}
      </button>
      {open ? (
        <div
          role="menu"
          className={clsx(
            "absolute z-50 grid min-w-[210px] gap-0.5 rounded-2xl border border-white/15 bg-night-700/95 p-1.5 shadow-[0_24px_60px_-20px_rgba(0,0,0,.9)]",
            up ? "bottom-[calc(100%+8px)] left-0" : "right-0 top-[calc(100%+8px)]",
          )}
        >
          {LANGS.map((option) => {
            const item = LANG_INFO[option];
            const on = option === lang;
            return (
              <button
                key={option}
                type="button"
                role="menuitemradio"
                aria-checked={on}
                onClick={() => {
                  setLang(option);
                  setOpen(false);
                }}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-night-fg hover:bg-white/5 focus-visible:bg-white/5 focus-visible:outline-none"
              >
                <span>
                  {item.name}
                  <small className="block font-mono text-[0.68rem] text-night-dim">{item.region}</small>
                </span>
                {on ? <span className="h-2 w-2 rounded-full bg-signal-400 shadow-[0_0_0_3px_rgba(198,244,50,.18)]" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
