"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useLocale } from "./LocaleProvider";
import { t, type Locale } from "@/lib/i18n";

type Theme = "dark" | "light";

function getStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem("alphacore-theme");
  return stored === "light" ? "light" : "dark";
}

function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");
  const { locale, setLocale } = useLocale();

  useEffect(() => {
    const initial = getStoredTheme();
    setTheme(initial);
    applyTheme(initial);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      localStorage.setItem("alphacore-theme", next);
      applyTheme(next);
      return next;
    });
  }, []);

  const toggleLocale = useCallback(() => {
    setLocale((prev: Locale) => (prev === "zh" ? "en" : "zh"));
  }, [setLocale]);

  return (
    <div className="flex items-center gap-2">
      <Button onClick={toggleLocale} size="sm">
        {locale === "zh" ? "EN" : "\u4E2D"}
      </Button>
      <Button
        onClick={toggleTheme}
        size="sm"
        aria-label={t(locale, "theme.toggle")}
      >
        {theme === "dark"
          ? t(locale, "theme.light")
          : t(locale, "theme.dark")}
      </Button>
    </div>
  );
}
