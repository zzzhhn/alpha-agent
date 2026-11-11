"use client";

/**
 * Sidebar — workstation lifecycle navigation.
 *
 * Each route shows the active-locale name first and the other locale beneath
 * it in the existing mono body size; English is never shrunk to fit. A route
 * shows a status marker only when the shared nav-status contract can explain a
 * concrete next step (see lib/nav-status.ts); unknown states stay neutral.
 *
 * Desktop users can collapse the panel to a 56px rail. The preference lives in
 * a cookie read by the server layout, so the first paint already has the right
 * width; collapsing never remounts the page content (only the grid track
 * changes), so filters, pagination and scroll position are preserved.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import {
  BellRing, BookOpen, ChartLine, Cpu, Database, FileText, Filter, FlaskConical,
  History, Library, ListOrdered, Network, PanelLeftClose, PanelLeftOpen,
  Settings, Sigma, Wallet, type LucideIcon,
} from "lucide-react";
import { useLocale } from "./LocaleProvider";
import SidebarAuthSlot from "./SidebarAuthSlot";
import { SystemHealthIndicator, useNavStatus } from "./SystemHealth";
import { TmTooltip } from "@/components/tm/TmTooltip";
import { TmIconButton } from "@/components/tm/TmButton";
import { NAV_GROUPS, isNavActive, navLabels, type NavItem, type NavItemId } from "@/lib/nav-items";
import {
  alertsSignal, evolutionSignal, picksSignal, type NavSignal, type NavSignals,
} from "@/lib/nav-status";
import type { SidebarMode } from "@/lib/sidebar-state";

const ICONS: Record<NavItemId, LucideIcon> = {
  picks: ListOrdered, paper: Wallet, alerts: BellRing,
  alpha: FlaskConical, backtest: ChartLine, screener: Filter, report: FileText,
  zoo: Library, evolution: History, brain: Cpu,
  guide: BookOpen, data: Database, methodology: Sigma, reference: Network, settings: Settings,
};

const TONE: Record<NavSignal["tone"], string> = {
  attention: "border-tm-accent/50 text-tm-accent",
  info: "border-tm-info/50 text-tm-info",
  warning: "border-tm-warn/60 text-tm-warn",
  negative: "border-tm-neg/60 text-tm-neg",
  muted: "border-tm-rule-2 text-tm-muted",
};

const DOT: Record<NavSignal["tone"], string> = {
  attention: "bg-tm-accent", info: "bg-tm-info", warning: "bg-tm-warn",
  negative: "bg-tm-neg", muted: "bg-tm-muted",
};

function useNavSignals(): NavSignals {
  const { locale } = useLocale();
  const nav = useNavStatus();
  const signals: NavSignals = {};
  const picks = picksSignal(nav.status?.picks ?? null, nav.statusFailed, locale);
  const alerts = alertsSignal(nav.attention, nav.attentionState, locale);
  const evolution = evolutionSignal(nav.status?.evolution ?? null, nav.statusFailed, locale);
  // Before the first response settles, show nothing rather than a guess.
  if (nav.status || nav.statusFailed) {
    if (picks) signals.picks = picks;
    if (evolution) signals.evolution = evolution;
  }
  if (alerts) signals.alerts = alerts;
  return signals;
}

export function Sidebar({
  mode,
  onToggle,
}: {
  readonly mode: SidebarMode;
  readonly onToggle: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const collapsed = mode === "collapsed";
  const signals = useNavSignals();

  const navigateWithHash = (event: React.MouseEvent<HTMLAnchorElement>, item: NavItem, signal?: NavSignal) => {
    if (!signal?.hash || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (isNavActive(pathname, item.href)) {
      const target = document.getElementById(signal.hash);
      if (target) {
        target.scrollIntoView({ block: "start" });
        target.focus({ preventScroll: true });
        return;
      }
    }
    router.push(`${item.href}#${signal.hash}`);
  };

  const toggleLabel = collapsed
    ? (zh ? "展开侧栏 Expand sidebar" : "Expand sidebar 展开侧栏")
    : (zh ? "收起侧栏 Collapse sidebar" : "Collapse sidebar 收起侧栏");
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      className="hidden h-full min-w-0 flex-col overflow-y-auto overflow-x-hidden border-r border-tm-rule bg-tm-bg font-tm-mono text-[12px] md:flex"
      aria-label={zh ? "主导航 Main navigation" : "Main navigation 主导航"}
      data-sidebar={mode}
    >
      <div className={clsx("flex border-b border-tm-rule", collapsed ? "justify-center py-2" : "justify-end px-2 py-1.5")}>
        <TmIconButton
          label={toggleLabel}
          title={toggleLabel}
          onClick={onToggle}
          aria-expanded={!collapsed}
          size="sm"
          icon={<ToggleIcon aria-hidden className="h-4 w-4" strokeWidth={1.75} />}
        />
      </div>

      <nav className={clsx("space-y-3 border-b border-tm-rule", collapsed ? "px-1.5 py-3" : "p-3")}>
        {NAV_GROUPS.map((group) => {
          const containsActive = group.items.some((item) => isNavActive(pathname, item.href));
          const groupSignal = group.items.map((item) => signals[item.id]).find(Boolean);
          const links = group.items.map((item) => {
            const active = isNavActive(pathname, item.href);
            const signal = signals[item.id];
            const { primary, secondary } = navLabels(item, locale);
            const Icon = ICONS[item.id];
            const statusText = signal ? `${signal.badge}. ${signal.detail}` : "";
            const accessibleName = `${primary} ${secondary}${statusText ? `, ${statusText}` : ""}`;
            const link = (
              <Link
                key={item.id}
                href={item.href}
                prefetch={false}
                aria-current={active ? "page" : undefined}
                aria-label={accessibleName}
                onClick={(event) => navigateWithHash(event, item, signal)}
                className={clsx(
                  "group relative flex w-full items-center transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-tm-accent motion-reduce:transition-none",
                  collapsed ? "h-9 justify-center" : "min-h-[40px] gap-2 px-1.5 py-1",
                  active ? "bg-tm-accent-soft text-tm-accent" : "text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg",
                )}
              >
                {active ? <span aria-hidden className="absolute inset-y-1 left-0 w-0.5 bg-tm-accent" /> : null}
                <Icon aria-hidden className={clsx("h-4 w-4 shrink-0", active ? "text-tm-accent" : "text-tm-muted group-hover:text-tm-fg-2")} strokeWidth={1.75} />
                {collapsed ? (
                  signal ? <span aria-hidden className={clsx("absolute right-1.5 top-1.5 h-1.5 w-1.5", DOT[signal.tone])} /> : null
                ) : (
                  <>
                    <span className="flex min-w-0 flex-1 flex-col leading-4">
                      <span className="truncate text-xs">{primary}</span>
                      <span className={clsx("truncate text-xs", active ? "text-tm-accent/70" : "text-tm-muted")}>{secondary}</span>
                    </span>
                    {signal ? (
                      <span aria-hidden className={clsx("shrink-0 border px-1 text-xs leading-4 tabular-nums", TONE[signal.tone])}>
                        {signal.badge}
                      </span>
                    ) : null}
                  </>
                )}
              </Link>
            );
            // Tooltip only where it adds information: the collapsed rail needs
            // the names; an expanded row needs it only to explain a marker.
            if (!collapsed && !signal) return link;
            return (
              <NavTooltip key={item.id} content={
                <span className="block">
                  <span className="block text-tm-fg">{primary} · {secondary}</span>
                  {signal ? <span className="mt-1 block text-tm-fg-2">{signal.detail}</span> : null}
                </span>
              }>
                {link}
              </NavTooltip>
            );
          });

          const groupLabel = zh ? `${group.zh} ${group.en}` : `${group.en} ${group.zh}`;
          if (collapsed) {
            return (
              <div key={group.id} role="group" aria-label={groupLabel} className="space-y-0.5 border-t border-tm-rule pt-2 first:border-t-0 first:pt-0">
                {links}
              </div>
            );
          }
          const heading = (
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span className="text-xs font-semibold tracking-[0.08em] text-tm-muted">{zh ? group.zh : group.en}</span>
              <span className="truncate text-xs text-tm-muted/70">{zh ? group.en : group.zh}</span>
            </span>
          );
          if (group.secondary) {
            return (
              <details key={group.id} open={containsActive || undefined}>
                <summary className="flex cursor-pointer list-none items-center gap-1.5 px-1.5 py-1 text-tm-muted hover:text-tm-fg-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-tm-accent">
                  <span aria-hidden className="w-2.5">{containsActive ? "▾" : "▸"}</span>
                  {heading}
                  {groupSignal && !containsActive ? (
                    <span aria-hidden className={clsx("ml-auto h-1.5 w-1.5 shrink-0", DOT[groupSignal.tone])} />
                  ) : null}
                </summary>
                <div className="mt-1 space-y-0.5">{links}</div>
              </details>
            );
          }
          return (
            <div key={group.id} role="group" aria-label={groupLabel}>
              <div className="mb-1 px-1.5">{heading}</div>
              <div className="space-y-0.5">{links}</div>
            </div>
          );
        })}
      </nav>

      <div className={clsx("mt-auto flex items-center gap-1.5 border-t border-tm-rule py-2 text-xs text-tm-muted", collapsed ? "justify-center px-1" : "px-3")}>
        <SystemHealthIndicator compact={collapsed} />
      </div>

      <SidebarAuthSlot compact={collapsed} />
    </aside>
  );
}

/** Tooltip wrapper that keeps the link itself as the only tab stop. */
function NavTooltip({ content, children }: { readonly content: React.ReactNode; readonly children: React.ReactNode }) {
  return (
    <TmTooltip content={content} placement="right" width={260} focusTarget="child" className="flex w-full">
      {children}
    </TmTooltip>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const signals = useNavSignals();
  return (
    <details className="relative z-50 border-b border-tm-rule bg-tm-bg md:hidden">
      <summary className="cursor-pointer list-none px-3 py-2 font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-accent">
        {zh ? "导航菜单 Navigation" : "Navigation 导航菜单"}
      </summary>
      <nav className="absolute inset-x-0 top-full grid max-h-[70vh] grid-cols-2 gap-3 overflow-y-auto border-b border-tm-rule bg-tm-bg p-3 shadow-[var(--tm-shadow-floating)]" aria-label={zh ? "导航菜单" : "Navigation menu"}>
        {NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <div className="mb-1 font-tm-mono text-xs tracking-[0.08em] text-tm-muted">
              {zh ? group.zh : group.en}
            </div>
            {group.items.map((item) => {
              const active = isNavActive(pathname, item.href);
              const signal = signals[item.id];
              const { primary, secondary } = navLabels(item, locale);
              return (
                <Link key={item.id} href={item.href} prefetch={false} aria-current={active ? "page" : undefined}
                  className={clsx("flex items-center justify-between gap-2 px-2 py-1.5 font-tm-mono text-xs", active ? "bg-tm-accent-soft text-tm-accent" : "text-tm-fg-2")}>
                  <span className="min-w-0">
                    <span className="block truncate">{primary}</span>
                    <span className="block truncate text-tm-muted">{secondary}</span>
                  </span>
                  {signal ? <span className={clsx("shrink-0 border px-1", TONE[signal.tone])}>{signal.badge}</span> : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </details>
  );
}
