"use client";

import { usePathname } from "next/navigation";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

const PAGE_TITLES: Record<string, string> = {
  "/backtest": "backtest.title",
  "/factors": "factors.title",
  "/gates": "gates.title",
  "/stress": "stress.title",
  "/activity": "activity.title",
};

export function Breadcrumb() {
  const pathname = usePathname();
  const { locale } = useLocale();

  const titleKey = PAGE_TITLES[pathname];
  const title = titleKey
    ? t(locale, titleKey as Parameters<typeof t>[1])
    : "AlphaCore";

  return (
    <nav
      className="flex items-center gap-2 text-base"
      aria-label="Current page"
    >
      <span className="text-[var(--muted)]">
        {t(locale, "group.research" as Parameters<typeof t>[1])}
      </span>
      <span className="text-[12px] text-[var(--muted)]" aria-hidden="true">
        {"\u203A"}
      </span>
      <span className="font-medium text-[var(--text)]">
        {title}
      </span>
    </nav>
  );
}
