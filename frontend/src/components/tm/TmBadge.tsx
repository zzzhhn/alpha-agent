"use client";

import { type HTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

export type TmBadgeTone =
  | "neutral"
  | "positive"
  | "warning"
  | "negative"
  | "info";

export interface TmBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  readonly tone?: TmBadgeTone;
  readonly children: ReactNode;
}

const TONE_STYLES: Record<TmBadgeTone, string> = {
  neutral: "border-tm-rule text-tm-fg-2 bg-tm-bg-2",
  positive: "border-tm-pos text-tm-pos bg-tm-pos-soft",
  warning: "border-tm-warn text-tm-warn bg-tm-warn-soft",
  negative: "border-tm-neg text-tm-neg bg-tm-neg-soft",
  info: "border-tm-info text-tm-info bg-tm-bg-2",
};

const TONE_MARKERS: Record<TmBadgeTone, string> = {
  neutral: "•",
  positive: "✓",
  warning: "!",
  negative: "×",
  info: "i",
};

/**
 * TmBadge — compact labelled state marker for workstation surfaces.
 *
 * The marker and caller-provided label make the state legible without
 * relying on color alone. It is intentionally non-interactive; use
 * TmChip or TmButton when the same visual needs an action.
 */
export function TmBadge({
  tone = "neutral",
  className,
  children,
  ...rest
}: TmBadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex min-h-6 items-center gap-1 border px-2 py-px font-tm-mono text-xs font-semibold leading-4 tracking-[0.04em] rounded-[2px]",
        TONE_STYLES[tone],
        className,
      )}
      data-tone={tone}
      {...rest}
    >
      <span aria-hidden="true" className="shrink-0">
        {TONE_MARKERS[tone]}
      </span>
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}
