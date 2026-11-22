"use client";

/*
 * Idiomas do painel: português (Brasil), inglês (EUA) e espanhol.
 *
 * Cada texto mora em lib/messages.ts como [pt-BR, en-US, es]. O TypeScript recusa chave desconhecida e
 * tradução faltando. A escolha fica no localStorage em `settlr-lang`, a mesma chave do site público, e
 * também chega do site pela entrega da sessão (/login#…&lang=en-US), porque o painel mora em outra origem.
 */

import { MESSAGES, type MessageKey } from "@/lib/messages";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const LANGS = ["pt-BR", "en-US", "es"] as const;
export type Lang = (typeof LANGS)[number];

export const LANG_INFO: Record<Lang, { code: string; name: string; region: string }> = {
  "pt-BR": { code: "PT-BR", name: "Português", region: "Brasil" },
  "en-US": { code: "EN-US", name: "English", region: "United States" },
  es: { code: "ES", name: "Español", region: "Latinoamérica" },
};

const STORAGE_KEY = "settlr-lang";
const INDEX: Record<Lang, 0 | 1 | 2> = { "pt-BR": 0, "en-US": 1, es: 2 };

export function isLang(value: unknown): value is Lang {
  return typeof value === "string" && (LANGS as readonly string[]).includes(value);
}

/* Idioma corrente fora do React: formatação de data/valor e rótulos usados por funções simples. */
let current: Lang = "pt-BR";

export function currentLang(): Lang {
  return current;
}

export type Vars = Record<string, string | number>;

/** Tradução sem hook. Use dentro de componentes que já chamam useI18n(), para re-renderizar na troca. */
export function tr(key: MessageKey, vars?: Vars, lang: Lang = current): string {
  let text: string = MESSAGES[key][INDEX[lang]];
  if (vars) for (const [name, value] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, String(value));
  return text;
}

export function saveLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* navegação privada: vale só nesta aba */
  }
}

function storedLang(): Lang | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isLang(value) ? value : null;
  } catch {
    return null;
  }
}

function browserLang(): Lang {
  const nav = typeof navigator === "undefined" ? "pt-BR" : navigator.language.toLowerCase();
  if (nav.startsWith("es")) return "es";
  if (nav.startsWith("en")) return "en-US";
  return "pt-BR";
}

type I18n = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, vars?: Vars) => string;
};

const I18nContext = createContext<I18n>({ lang: "pt-BR", setLang: () => {}, t: (key, vars) => tr(key, vars, "pt-BR") });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("pt-BR");
  current = lang;

  useEffect(() => {
    const initial = storedLang() ?? browserLang();
    if (initial !== "pt-BR") setLangState(initial);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang === "es" ? "es" : lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    saveLang(next);
    setLangState(next);
  }, []);

  const value = useMemo<I18n>(() => ({ lang, setLang, t: (key, vars) => tr(key, vars, lang) }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
