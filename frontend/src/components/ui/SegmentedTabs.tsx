"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * SegmentedTabs: canonical high-affordance tab bar.
 *
 * The old style (thin accent underline + accent text on the active tab) was
 * too quiet: users couldn't tell the bar was switchable. This version makes
 * the selection unmistakable:
 *   - active segment uses the content background, accent text, and a 2px
 *     accent bar on the shared bottom rule, without competing with the page's
 *     filled primary action;
 *   - inactive segments are muted but get a clear hover background, so they
 *     read as pressable;
 *   - vertical dividers between segments make the bar read as a control.
 *
 * Same component, same look on both pages → consistent affordance.
 */
export interface SegmentedTabItem<K extends string> {
  readonly key: K;
  readonly label: string;
  /** Optional trailing node, such as a count pill or warning badge. */
  readonly badge?: ReactNode;
}

export function SegmentedTabs<K extends string>({
  items,
  active,
  onChange,
  ariaLabel,
  idBase,
  className = "",
}: {
  readonly items: ReadonlyArray<SegmentedTabItem<K>>;
  readonly active: K;
  readonly onChange: (key: K) => void;
  readonly ariaLabel?: string;
  readonly idBase?: string;
  readonly className?: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function moveFocus(index: number, event: KeyboardEvent<HTMLButtonElement>) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % items.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else return;
    event.preventDefault();
    const item = items[next];
    if (!item) return;
    onChange(item.key);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`flex items-stretch divide-x divide-tm-rule/50 overflow-x-auto border-b border-tm-rule bg-tm-bg-2 ${className}`}
    >
      {items.map((item, index) => {
        const isActive = item.key === active;
        const tabId = idBase ? `${idBase}-tab-${item.key}` : undefined;
        const panelId = idBase ? `${idBase}-panel-${item.key}` : undefined;
        return (
          <button
            key={item.key}
            ref={(node) => { refs.current[index] = node; }}
            id={tabId}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={panelId}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(item.key)}
            onKeyDown={(event) => moveFocus(index, event)}
            className={[
              "relative flex h-8 items-center gap-1.5 whitespace-nowrap px-3 font-tm-mono text-[11px] uppercase tracking-[0.06em] transition-colors",
              isActive
                ? "bg-tm-bg font-semibold text-tm-accent after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-tm-accent"
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
