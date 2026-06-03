"use client";

import type { ReactNode } from "react";

/**
 * HoverTip - wraps arbitrary trigger content and reveals a tooltip instantly
 * on hover/focus. Unlike the native `title` attribute (which the browser
 * delays ~1s before showing), this is pure CSS group-hover so it appears the
 * moment the pointer lands. Sibling of InfoTooltip, but wraps any child
 * instead of rendering a fixed Info icon.
 *
 * Uses a NAMED group (`group/tip`) so nesting inside another `group` (e.g. a
 * hoverable table row or feed card) never cross-triggers.
 *
 * The popover is `pointer-events-none` so it never traps the mouse, and
 * `z-50` so it floats above neighbouring cards. `content` may include `\n`
 * line breaks (rendered via `whitespace-pre-line`).
 */
export function HoverTip({
  children,
  content,
  placement = "bottom",
  width = "w-56",
  className = "",
}: {
  children: ReactNode;
  content: string;
  placement?: "bottom" | "top" | "right" | "left";
  width?: string;
  className?: string;
}) {
  const pos =
    placement === "right"
      ? "left-full top-1/2 ml-2 -translate-y-1/2"
      : placement === "left"
        ? "right-full top-1/2 mr-2 -translate-y-1/2"
        : placement === "top"
          ? "bottom-full left-1/2 mb-1 -translate-x-1/2"
          : "top-full left-1/2 mt-1 -translate-x-1/2";
  return (
    <span className={`group/tip relative inline-flex items-center ${className}`}>
      {children}
      <span
        role="tooltip"
        className={`invisible absolute ${pos} ${width} z-50 rounded border border-tm-rule bg-tm-bg-2 p-2 text-[11px] leading-snug text-tm-fg opacity-0 shadow-lg transition-opacity duration-75 group-hover/tip:visible group-hover/tip:opacity-100 group-focus-within/tip:visible group-focus-within/tip:opacity-100 whitespace-pre-line pointer-events-none`}
      >
        {content}
      </span>
    </span>
  );
}
