"use client";

/**
 * Sidebar — workstation lifecycle nav (Variation C, Stage 2).
 *
 * 200-wide terminal panel with a single LIFECYCLE section (9 items
 * matching the existing routes). Each item:
 *   - 11.5px JetBrains Mono text
 *   - Marker glyph: ▶ for current page, · for others
 *   - Hover: bg-tm-bg-2 + text-tm-fg
 *   - Current: bg-tm-accent-soft + text-tm-accent
 *
 * Routing is unchanged from Stage 1 — same `<Link prefetch>` behavior
 * (explicit `prefetch={true}` was set in the prior phase 11 perf pass
 * to force RSC prefetch on dynamic routes; preserved here).
 *
 * Brand block + locale/theme toggles moved OUT of the sidebar in Stage
 * 2 and now live in the Topbar titlebar above. The footer "system
 * online" pulse stays as a subtle liveness indicator at the bottom.
 *
 * The design's second sidebar section ("FACTORS" — list of recently
 * used factors) is deliberately dropped for now: it duplicates the
 * /factors page and adds maintenance overhead with no clear win at
 * 200px width. Re-evaluate during Stage 3 Factors port.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";
import SidebarAuthSlot from "./SidebarAuthSlot";

interface NavItem {
  readonly id: string;
  readonly href: string;
  readonly labelKey: string;
}

interface NavGroup {
  readonly titleKey: string;
  readonly items: ReadonlyArray<NavItem>;
  readonly secondary?: boolean;
}

// P2-1: regrouped from a flat LIFECYCLE list into a value-prop information
// architecture. RESEARCH leads (Alpha / Hypothesis Lab is the platform's
// differentiator), then DECISIONS (the act-on-it surfaces), then REFERENCE.
// `id` is informational; the active marker is pathname === item.href.
const NAV_GROUPS: ReadonlyArray<NavGroup> = [
  {
    titleKey: "nav.group.workflow",
    items: [
      { id: "picks", href: "/picks", labelKey: "nav.picks" },
      { id: "paper", href: "/paper", labelKey: "nav.paper" },
      { id: "alerts", href: "/alerts", labelKey: "nav.alerts" },
    ],
  },
  {
    titleKey: "nav.group.research",
    items: [
      { id: "alpha", href: "/alpha", labelKey: "lifecycle.alpha" },
      { id: "backtest", href: "/backtest", labelKey: "lifecycle.backtest" },
      { id: "screener", href: "/screener", labelKey: "lifecycle.screener" },
      { id: "report", href: "/report", labelKey: "lifecycle.report" },
    ],
  },
  {
    titleKey: "nav.group.advanced",
    secondary: true,
    items: [
      { id: "zoo", href: "/factors", labelKey: "lifecycle.zoo" },
      { id: "evolution", href: "/evolution", labelKey: "nav.evolution" },
      { id: "brain", href: "/brain", labelKey: "nav.brain" },
    ],
  },
  {
    titleKey: "nav.group.reference",
    items: [
      { id: "data", href: "/data", labelKey: "lifecycle.data" },
      { id: "methodology", href: "/methodology", labelKey: "lifecycle.methodology" },
      { id: "settings", href: "/settings", labelKey: "lifecycle.settings" },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { locale } = useLocale();

  return (
    <aside
      className="hidden h-full w-[200px] flex-col overflow-y-auto border-r border-tm-rule bg-tm-bg font-tm-mono text-[12px] md:flex"
      role="navigation"
      aria-label="Lifecycle navigation"
    >
      <div className="border-b border-tm-rule p-3 space-y-3">
        {NAV_GROUPS.map((group) => {
          const containsActive = group.items.some((item) => pathname === item.href);
          const links = group.items.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.id}
                href={item.href}
                prefetch={false}
                aria-current={isActive ? "page" : undefined}
                className={clsx(
                  "flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] transition-colors",
                  isActive
                    ? "bg-tm-accent-soft text-tm-accent"
                    : "text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg",
                )}
              >
                <span className={clsx("w-[10px] text-center", isActive ? "text-tm-accent" : "text-tm-muted")} aria-hidden="true">
                  {isActive ? "▶" : "·"}
                </span>
                <span>{t(locale, item.labelKey as Parameters<typeof t>[1])}</span>
              </Link>
            );
          });
          if (group.secondary) {
            return (
              <details key={group.titleKey} open={containsActive}>
                <summary className="cursor-pointer list-none px-1.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-tm-muted hover:text-tm-fg-2">
                  {containsActive ? "▾" : "▸"} {t(locale, group.titleKey as Parameters<typeof t>[1])}
                </summary>
                <div className="mt-1">{links}</div>
              </details>
            );
          }
          return (
            <div key={group.titleKey}>
              <div className="mb-1 px-1.5 text-[10px] font-semibold tracking-[0.12em] text-tm-muted">
                {t(locale, group.titleKey as Parameters<typeof t>[1])}
              </div>
              {links}
            </div>
          );
        })}
      </div>

      <div className="mt-auto flex items-center gap-1.5 border-t border-tm-rule px-3 py-2 text-[10px] text-tm-muted">
        <span
          className="h-1.5 w-1.5 animate-tm-pulse bg-tm-accent"
          aria-hidden="true"
        />
        {t(locale, "brand.systemOnline" as Parameters<typeof t>[1])}
      </div>

      <SidebarAuthSlot />
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  const { locale } = useLocale();
  return (
    <details className="relative z-50 border-b border-tm-rule bg-tm-bg md:hidden">
      <summary className="cursor-pointer list-none px-3 py-2 font-tm-mono text-[10.5px] uppercase tracking-[0.08em] text-tm-accent">
        {t(locale, "nav.mobile_menu")}
      </summary>
      <nav className="absolute inset-x-0 top-full grid max-h-[70vh] grid-cols-2 gap-3 overflow-y-auto border-b border-tm-rule bg-tm-bg p-3 shadow-lg" aria-label={t(locale, "nav.mobile_menu")}>
        {NAV_GROUPS.map((group) => (
          <div key={group.titleKey}>
            <div className="mb-1 font-tm-mono text-[9.5px] uppercase tracking-[0.1em] text-tm-muted">
              {t(locale, group.titleKey as Parameters<typeof t>[1])}
            </div>
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link key={item.id} href={item.href} prefetch={false} className={clsx("block px-2 py-1.5 font-tm-mono text-[11px]", active ? "bg-tm-accent-soft text-tm-accent" : "text-tm-fg-2")}>
                  {t(locale, item.labelKey as Parameters<typeof t>[1])}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </details>
  );
}
