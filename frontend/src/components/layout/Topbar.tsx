"use client";

/**
 * Topbar — workstation titlebar (Variation C, Stage 2).
 *
 * Replaces the previous Breadcrumb + ThemeToggle fragment that lived
 * inline in (dashboard)/layout.tsx. Holds:
 *   - Brand: ▲ logo + "ALPHACORE.WORKSTATION" name
 *   - Status: pulse LED + "system online" / 系统在线
 *   - Locale toggle (EN / 中)
 *   - Theme toggle (LT / DK)
 *
 * State management is unchanged from the legacy ThemeToggle component:
 *   - Theme persists in `localStorage["alphacore-theme"]`
 *   - Locale persists via the LocaleProvider context (which itself
 *     persists to localStorage via lib/i18n)
 *
 * The legacy ThemeToggle.tsx and Breadcrumb.tsx components are kept on
 * disk during the redesign branch in case any other route imports them;
 * they will be removed in Stage 5 (polish) once a full grep confirms no
 * remaining consumers.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "./LocaleProvider";
import { t, type Locale } from "@/lib/i18n";

type Theme = "dark" | "light";

function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return localStorage.getItem("alphacore-theme") === "light" ? "light" : "dark";
}

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

interface ToggleButtonProps {
  readonly active: boolean;
  readonly onClick: () => void;
  readonly children: React.ReactNode;
  readonly ariaLabel?: string;
}

function ToggleButton({ active, onClick, children, ariaLabel }: ToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      aria-pressed={active}
      className={[
        "px-2 py-[3px] text-[10.5px] tracking-[0.04em] cursor-pointer transition-colors",
        active
          ? "bg-tm-accent-soft text-tm-accent font-semibold"
          : "text-tm-muted hover:text-tm-fg",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function Topbar() {
  const { locale, setLocale } = useLocale();
  const [theme, setTheme] = useState<Theme>("dark");

  // Hydrate stored theme on mount; first render uses "dark" to match
  // the SSR `data-theme="dark"` on <html> from app/layout.tsx, avoiding
  // a flash before the useEffect runs.
  useEffect(() => {
    const initial = getStoredTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  const switchTheme = useCallback((next: Theme) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("alphacore-theme", next);
    }
    applyTheme(next);
    setTheme(next);
  }, []);

  const switchLocale = useCallback(
    (next: Locale) => setLocale(next),
    [setLocale],
  );

  return (
    <header
      className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[11px]"
      role="banner"
    >
      <div className="flex items-center gap-3.5 text-tm-fg-2">
        <span className="text-[14px] text-tm-accent" aria-hidden="true">
          ▲
        </span>
        <span className="font-semibold tracking-[0.04em] text-tm-fg">
          ALPHACORE.WORKSTATION
        </span>
        <span className="hidden items-center gap-1.5 text-tm-muted md:flex">
          <span
            className="h-1.5 w-1.5 animate-tm-pulse bg-tm-accent"
            aria-hidden="true"
          />
          {t(locale, "brand.systemOnline" as Parameters<typeof t>[1])}
        </span>
      </div>

      <div className="flex gap-2">
        {/* Locale toggle — Stage 2 keeps the same persistence path
            (lib/i18n setLocaleToStorage via the provider). */}
        <div
          className="inline-flex border border-tm-rule"
          role="group"
          aria-label="Locale"
        >
          <ToggleButton
            active={locale === "en"}
            onClick={() => switchLocale("en")}
            ariaLabel="English"
          >
            EN
          </ToggleButton>
          <ToggleButton
            active={locale === "zh"}
            onClick={() => switchLocale("zh")}
            ariaLabel="中文"
          >
            中
          </ToggleButton>
        </div>

        {/* Theme toggle — split into two explicit LT / DK buttons matching
            the design (rather than the legacy single "Light"/"Dark" button)
            so the active state is always visible without needing to click
            to discover. */}
        <div
          className="inline-flex border border-tm-rule"
          role="group"
          aria-label={t(locale, "theme.toggle" as Parameters<typeof t>[1])}
        >
          <ToggleButton
            active={theme === "light"}
            onClick={() => switchTheme("light")}
            ariaLabel={t(locale, "theme.light" as Parameters<typeof t>[1])}
          >
            LT
          </ToggleButton>
          <ToggleButton
            active={theme === "dark"}
            onClick={() => switchTheme("dark")}
            ariaLabel={t(locale, "theme.dark" as Parameters<typeof t>[1])}
          >
            DK
          </ToggleButton>
        </div>
      </div>
    </header>
  );
}
