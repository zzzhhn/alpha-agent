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

interface NavItem {
  readonly id: string;
  readonly href: string;
  readonly labelKey: string;
}

// Order matches the design's LIFECYCLE list. `id` is informational
// only (the marker glyph is determined by `pathname === item.href`,
// not by id). All 9 routes preserved from the legacy sidebar.
const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { id: "data", href: "/data", labelKey: "lifecycle.data" },
  { id: "alpha", href: "/alpha", labelKey: "lifecycle.alpha" },
  { id: "signal", href: "/signal", labelKey: "lifecycle.signal" },
  { id: "backtest", href: "/backtest", labelKey: "lifecycle.backtest" },
  { id: "report", href: "/report", labelKey: "lifecycle.report" },
  { id: "zoo", href: "/factors", labelKey: "lifecycle.zoo" },
  { id: "screener", href: "/screener", labelKey: "lifecycle.screener" },
  { id: "methodology", href: "/methodology", labelKey: "lifecycle.methodology" },
  { id: "settings", href: "/settings", labelKey: "lifecycle.settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { locale } = useLocale();

  return (
    <aside
      className="flex h-full w-[200px] flex-col overflow-y-auto border-r border-tm-rule bg-tm-bg font-tm-mono text-[12px]"
      role="navigation"
      aria-label="Lifecycle navigation"
    >
      <div className="border-b border-tm-rule p-3">
        <div className="mb-2 px-1.5 text-[10px] font-semibold tracking-[0.12em] text-tm-muted">
          LIFECYCLE
        </div>
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.id}
              href={item.href}
              prefetch={true}
              aria-current={isActive ? "page" : undefined}
              className={clsx(
                "flex w-full items-center gap-2 px-1.5 py-1 text-[11.5px] transition-colors",
                isActive
                  ? "bg-tm-accent-soft text-tm-accent"
                  : "text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg",
              )}
            >
              <span
                className={clsx(
                  "w-[10px] text-center",
                  isActive ? "text-tm-accent" : "text-tm-muted",
                )}
                aria-hidden="true"
              >
                {isActive ? "▶" : "·"}
              </span>
              <span>
                {t(locale, item.labelKey as Parameters<typeof t>[1])}
              </span>
            </Link>
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
    </aside>
  );
}
