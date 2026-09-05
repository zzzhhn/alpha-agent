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
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { SystemHealthIndicator } from "./SystemHealth";

type Theme = "dark" | "light";

function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  return localStorage.getItem("alphacore-theme") === "light" ? "light" : "dark";
}

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
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
      className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-xs"
      role="banner"
    >
      <div className="flex items-center gap-3.5 text-tm-fg-2">
        <span className="text-[14px] text-tm-accent" aria-hidden="true">
          ▲
        </span>
        <span className="font-semibold tracking-[0.04em] text-tm-fg">
          <span className="sm:hidden">ALPHACORE</span>
          <span className="hidden sm:inline">ALPHACORE.WORKSTATION</span>
        </span>
        <span className="hidden items-center gap-1.5 text-tm-muted md:flex">
          <SystemHealthIndicator />
        </span>
      </div>

      <div className="flex gap-2">
        <TmToggleGroup<Locale>
          value={locale}
          onChange={switchLocale}
          ariaLabel="Locale"
          options={[
            { value: "en", label: "EN", ariaLabel: "English" },
            { value: "zh", label: "中", ariaLabel: "中文" },
          ]}
        />

        <TmToggleGroup<Theme>
          value={theme}
          onChange={switchTheme}
          ariaLabel={t(locale, "theme.toggle" as Parameters<typeof t>[1])}
          options={[
            {
              value: "light",
              label: "LT",
              ariaLabel: t(locale, "theme.light" as Parameters<typeof t>[1]),
            },
            {
              value: "dark",
              label: "DK",
              ariaLabel: t(locale, "theme.dark" as Parameters<typeof t>[1]),
            },
          ]}
        />
      </div>
    </header>
  );
}
