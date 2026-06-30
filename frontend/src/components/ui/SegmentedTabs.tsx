"use client";

import type { ReactNode } from "react";

/**
 * SegmentedTabs — a high-affordance tab bar shared by /backtest and /factors.
 *
 * The old style (thin accent underline + accent text on the active tab) was
 * too quiet: users couldn't tell the bar was switchable. This version makes
 * the selection unmistakable —
 *   - active segment is FILLED (bg-tm-bg, matching the content area below it),
 *     bold, accent-colored, with a 2px accent bar on the shared bottom rule;
 *   - inactive segments are muted but get a clear hover background, so they
 *     read as pressable;
 *   - vertical dividers between segments make the bar read as a control.
 *
 * Same component, same look on both pages → consistent affordance.
 */
export interface SegmentedTabItem<K extends string> {
  readonly key: K;
  readonly label: string;
  /** Optional trailing node (e.g. a count pill or ⚠ badge). */
  readonly badge?: ReactNode;
}

export function SegmentedTabs<K extends string>({
  items,
  active,
  onChange,
  ariaLabel,
  className = "",
}: {
  readonly items: ReadonlyArray<SegmentedTabItem<K>>;
  readonly active: K;
  readonly onChange: (key: K) => void;
  readonly ariaLabel?: string;
  readonly className?: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`flex items-stretch divide-x divide-tm-rule/50 overflow-x-auto border-b border-tm-rule bg-tm-bg-2 ${className}`}
    >
      {items.map((item) => {
        const isActive = item.key === active;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(item.key)}
            className={[
              "relative flex items-center gap-1.5 whitespace-nowrap px-4 py-2.5 font-tm-mono text-[11px] uppercase tracking-[0.06em] transition-colors",
              isActive
                ? "bg-tm-accent font-semibold text-tm-bg"
                : "font-medium text-tm-muted hover:bg-tm-bg-3 hover:text-tm-fg",
            ].join(" ")}
          >
            <span>{item.label}</span>
            {item.badge}
          </button>
        );
      })}
    </div>
  );
}
