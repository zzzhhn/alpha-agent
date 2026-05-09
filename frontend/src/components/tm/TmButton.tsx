"use client";

/**
 * TmButton — workstation-aesthetic action button.
 *
 * Three variants:
 *   - "primary"  : solid accent green (tm-go pattern from the design CSS).
 *                  Used for the single "GO" action of a pane (Save, Run,
 *                  Translate, Generate).
 *   - "secondary": hairline-bordered ghost. Used for "Test connection",
 *                  "Cancel", and other support actions.
 *   - "ghost"    : transparent text-only. Used for "Clear", "Reset",
 *                  destructive-but-low-stakes actions.
 *
 * Disabled state mirrors the design's `.tm-go:disabled` rule: muted
 * colors and the `progress` cursor (slightly different from the legacy
 * `not-allowed` so users see "still working" rather than "you can't").
 *
 * Deliberately avoiding the shared `ui/Button` so each page port can
 * proceed without forcing a synchronous color change on un-ported pages.
 * Stage 5 will reconcile if both buttons need to coexist.
 */

import { type ButtonHTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

type Variant = "primary" | "secondary" | "ghost";

interface TmButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: Variant;
  readonly children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-tm-accent text-tm-bg hover:opacity-90 disabled:bg-tm-bg-3 disabled:text-tm-muted disabled:cursor-progress",
  secondary:
    "border border-tm-rule text-tm-fg-2 hover:border-tm-rule-2 hover:text-tm-fg disabled:text-tm-muted disabled:cursor-progress",
  ghost:
    "text-tm-muted hover:text-tm-fg disabled:opacity-50",
};

export function TmButton({
  variant = "primary",
  className,
  type = "button",
  children,
  ...rest
}: TmButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        "font-tm-mono text-[11px] font-semibold tracking-[0.06em] cursor-pointer transition-colors px-3 py-1.5",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
