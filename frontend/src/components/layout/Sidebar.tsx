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
    labelKey: "group.research",
    items: [
      {
        id: "backtest",
        labelKey: "nav.backtest",
        href: "/backtest",
        emoji: "📉",
      },
      {
        id: "factors",
        labelKey: "nav.factors",
        href: "/factors",
        emoji: "🧬",
        badge: "New",
      },
      {
        id: "gates",
        labelKey: "nav.gates",
        href: "/gates",
        emoji: "🚦",
        badge: "New",
      },
      {
        id: "stress",
        labelKey: "nav.stress",
        href: "/stress",
        emoji: "🌪️",
        badge: "New",
      },
    ],
  },
  {
    labelKey: "group.analysis",
    items: [
      {
        id: "inference",
        labelKey: "nav.inference",
        href: "/inference",
        emoji: "\uD83E\uDDE0",
        badge: "Core",
      },
      {
        id: "market",
        labelKey: "nav.market",
        href: "/market",
        emoji: "\uD83D\uDCC8",
      },
      {
        id: "alpha",
        labelKey: "nav.alpha",
        href: "/alpha",
        emoji: "\uD83C\uDFAF",
        badge: "Core",
      },
    ],
  },
  {
    labelKey: "group.execution",
    items: [
      {
        id: "portfolio",
        labelKey: "nav.portfolio",
        href: "/portfolio",
        emoji: "\uD83D\uDCBC",
      },
      {
        id: "orders",
        labelKey: "nav.orders",
        href: "/orders",
        emoji: "\u26A1",
      },
    ],
  },
  {
    labelKey: "group.infra",
    items: [
      {
        id: "gateway",
        labelKey: "nav.gateway",
        href: "/gateway",
        emoji: "\uD83D\uDD27",
      },
      {
        id: "audit",
        labelKey: "nav.audit",
        href: "/audit",
        emoji: "\uD83D\uDCDC",
      },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { locale } = useLocale();

  return (
    <aside
      className="flex h-screen w-[260px] flex-col border-r border-border bg-sidebar-bg"
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5 border-b border-border px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-indigo-500 text-[13px] font-bold text-white">
          AC
        </div>
        <span className="text-base font-bold text-text">
          {t(locale, "brand.name")}
        </span>
        <span className="ml-1 rounded bg-accent-glow px-1.5 py-px text-[10px] text-accent">
          {t(locale, "brand.tag")}
        </span>
      </div>

      {/* Nav Groups */}
      <nav className="flex-1 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.labelKey} className="px-3 pt-4 pb-1">
            <div className="mb-1 px-2 text-[11px] uppercase tracking-wide text-muted">
              {t(locale, group.labelKey as Parameters<typeof t>[1])}
            </div>
            {group.items.map((item, itemIndex) => {
              const isActive = pathname === item.href;
              const isLastInGroup =
                itemIndex === group.items.length - 1;

              return (
                <Link
                  key={item.id}
                  href={item.href}
                  className={clsx(
                    "relative mb-0.5 flex items-center gap-2.5 rounded-lg border-l-[3px] px-3 py-2.5 text-[13px] transition-all duration-200",
                    isActive
                      ? "sidebar-active-bg border-l-[var(--sidebar-active-border)] font-semibold text-text"
                      : "border-l-transparent text-muted hover:bg-white/[0.03] hover:text-text-secondary"
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  {/* Pipeline connector line */}
                  {!isLastInGroup && (
                    <span
                      className="absolute left-[22px] top-full h-1.5 w-px bg-border opacity-50"
                      aria-hidden="true"
                    />
                  )}

                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center text-[15px]"
                    aria-hidden="true"
                  >
                    {item.emoji}
                  </span>
                  <span>
                    {t(
                      locale,
                      item.labelKey as Parameters<typeof t>[1]
                    )}
                  </span>
                  {item.badge && (
                    <span className="ml-auto rounded bg-accent-glow px-1.5 py-px text-[10px] text-accent">
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
      <div className="flex items-center gap-2 border-t border-border px-5 py-4 text-xs text-muted">
        <span className="h-2 w-2 animate-pulse rounded-full bg-green" />
        {t(locale, "brand.systemOnline")}
      </div>
    </aside>
  );
}
