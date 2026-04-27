"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

interface SidebarNavItem {
  readonly id: string;
  readonly labelKey: string;
  readonly href: string;
  readonly emoji: string;
  readonly badge?: string;
}

interface SidebarGroup {
  readonly labelKey: string;
  readonly items: readonly SidebarNavItem[];
}

const NAV_GROUPS: readonly SidebarGroup[] = [
  {
    labelKey: "group.lifecycle",
    items: [
      { id: "data", labelKey: "lifecycle.data", href: "/data", emoji: "🗂️" },
      { id: "alpha", labelKey: "lifecycle.alpha", href: "/alpha", emoji: "🧬" },
      { id: "signal", labelKey: "lifecycle.signal", href: "/signal", emoji: "📡" },
      {
        id: "backtest",
        labelKey: "lifecycle.backtest",
        href: "/backtest",
        emoji: "📉",
      },
      { id: "report", labelKey: "lifecycle.report", href: "/report", emoji: "📑" },
      { id: "zoo", labelKey: "lifecycle.zoo", href: "/factors", emoji: "🦄" },
      { id: "screener", labelKey: "lifecycle.screener", href: "/screener", emoji: "🎯" },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { locale } = useLocale();

  return (
    <aside
      className="flex h-screen w-[260px] flex-col border-r border-[var(--border-solid)] bg-[var(--sidebar-bg)]"
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 border-b border-[var(--border)] px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--accent)] to-[var(--accent-hover)] text-[15px] font-bold text-white">
          AC
        </div>
        <span className="text-lg font-semibold text-[var(--text)]">
          {t(locale, "brand.name")}
        </span>
        <span className="ml-1 rounded bg-[var(--accent-glow)] px-1.5 py-px text-[12px] text-[var(--accent)]">
          {t(locale, "brand.tag")}
        </span>
      </div>

      {/* Nav Groups */}
      <nav className="flex-1 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.labelKey} className="px-3 pt-5 pb-1">
            <div className="mb-1.5 px-2 text-[13px] font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
              {t(locale, group.labelKey as Parameters<typeof t>[1])}
            </div>
            {group.items.map((item) => {
              const isActive = pathname === item.href;

              return (
                <Link
                  key={item.id}
                  href={item.href}
                  className={clsx(
                    "relative mb-0.5 flex items-center gap-2.5 rounded-lg border-l-[3px] px-3 py-2 text-[15px] transition-all duration-150",
                    isActive
                      ? "sidebar-active-bg border-l-[var(--sidebar-active-border)] font-semibold text-[var(--text)]"
                      : "border-l-transparent text-[var(--muted)] hover:bg-[rgba(255,255,255,0.03)] hover:text-[var(--text-secondary)]"
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center text-[17px]"
                    aria-hidden="true"
                  >
                    {item.emoji}
                  </span>
                  <span>{t(locale, item.labelKey as Parameters<typeof t>[1])}</span>
                  {item.badge && (
                    <span className="ml-auto rounded bg-[var(--accent-glow)] px-1.5 py-px text-[12px] text-[var(--accent)]">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer status */}
      <div className="flex items-center gap-2 border-t border-[var(--border)] px-5 py-3 text-sm text-[var(--muted)]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--green)]" />
        {t(locale, "brand.systemOnline")}
      </div>
    </aside>
  );
}
