"use client";

/**
 * TmSubbar + TmChip — workstation control strip primitives.
 *
 * The subbar is the thin horizontal band that sits between the page
 * chrome and the first pane. It carries the page's "active context"
 * controls — current universe, factor, date, and a status pill — laid
 * out as a single inline row of K/V labels separated by `│` glyphs.
 *
 * Mirrors `.tm-subbar` from styles-screens.css.
 *
 * Children:
 *   - `<TmSubbarKV label="UNIVERSE" value="SP500_subset" />`
 *   - `<TmChip on={...} onClick={...}>SP100</TmChip>`
 *   - `<TmSubbarSep />`
 *   - `<TmSubbarSpacer />` to push trailing items right
 *   - `<TmStatusPill tone="ok|warn|err">SIGNAL FRESH · 2m AGO</TmStatusPill>`
 */

import { type ReactNode, type ButtonHTMLAttributes } from "react";
import clsx from "clsx";

interface TmSubbarProps {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmSubbar({ children, className }: TmSubbarProps) {
  return (
    <div
      className={clsx(
        "flex min-h-[28px] items-center gap-3 bg-tm-bg-2 px-3 py-1 font-tm-mono text-[10.5px] tracking-[0.04em] text-tm-muted",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TmSubbarKVProps {
  readonly label: ReactNode;
  readonly value: ReactNode;
}

export function TmSubbarKV({ label, value }: TmSubbarKVProps) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-tm-muted">{label}</span>
      <span className="tabular-nums text-tm-fg">{value}</span>
    </span>
  );
}

export function TmSubbarSep() {
  return (
    <span className="select-none text-tm-rule-2" aria-hidden="true">
      │
    </span>
  );
}

export function TmSubbarSpacer() {
  return <span className="flex-1" aria-hidden="true" />;
}

// ── Chips ────────────────────────────────────────────────────────────

interface TmChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly on?: boolean;
  readonly tone?: "default" | "warn";
  readonly count?: ReactNode;
  readonly children: ReactNode;
}

export function TmChip({
  on = false,
  tone = "default",
  count,
  className,
  children,
  type = "button",
  ...rest
}: TmChipProps) {
  const tonePalette =
    tone === "warn"
      ? "border-tm-warn text-tm-warn bg-tm-bg-2"
      : on
        ? "border-tm-accent text-tm-accent bg-tm-accent-soft"
        : "border-tm-rule text-tm-fg-2 bg-tm-bg-2 hover:text-tm-fg";
  return (
    <button
      type={type}
      className={clsx(
        "inline-flex items-center gap-1.5 border px-2 py-px font-tm-mono text-[10.5px] leading-4 transition-colors",
        tonePalette,
        className,
      )}
      {...rest}
    >
      {children}
      {count !== undefined && count !== null && (
        <span className="text-[9.5px] text-tm-muted">{count}</span>
      )}
    </button>
  );
}

// ── Status pill ──────────────────────────────────────────────────────

interface TmStatusPillProps {
  readonly tone?: "ok" | "warn" | "err";
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmStatusPill({
  tone = "ok",
  children,
  className,
}: TmStatusPillProps) {
  const palette =
    tone === "warn"
      ? "text-tm-warn bg-tm-warn-soft"
      : tone === "err"
        ? "text-tm-neg bg-tm-neg-soft"
        : "text-tm-accent bg-tm-accent-soft";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2 py-px font-tm-mono text-[10px] font-semibold tracking-[0.04em]",
        palette,
        className,
      )}
    >
      {children}
    </span>
  );
}
