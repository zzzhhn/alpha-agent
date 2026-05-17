"use client";

import { Info } from "lucide-react";

/**
 * InfoTooltip - small Info icon that reveals a popover on hover/focus.
 *
 * `content` may include `\n` line breaks; we use `whitespace-pre-line` so
 * those render as actual line breaks. Tailwind-only, no Radix/Headless UI
 * dependency. The popover is `pointer-events-none` so it never traps the
 * mouse, and `z-50` so it floats above nearby cards.
 *
 * placement controls anchor direction. "bottom" (default) centers the
 * tooltip below the icon and works in wide-column contexts like the
 * AttributionTable. "right" anchors the tooltip to the right of the icon
 * and is required in narrow-column contexts like the ActionBox (which
 * lives in a col-span-3 sidebar). Without "right" the tooltip's left
 * half overflows the sidebar bounds and gets visually clipped by the
 * outer nav.
 */
export function InfoTooltip({
  content,
  iconSize = 12,
  placement = "bottom",
  className = "",
}: {
  content: string;
  iconSize?: number;
  placement?: "bottom" | "right";
  className?: string;
}) {
  const popoverPlacement =
    placement === "right"
      ? "left-full top-1/2 ml-2 -translate-y-1/2"
      : "left-1/2 top-full -translate-x-1/2 mt-1";
  return (
    <span className={`relative inline-flex items-center group ${className}`}>
      <Info
        size={iconSize}
        tabIndex={0}
        aria-label="more info"
        className="text-tm-muted hover:text-tm-fg focus:text-tm-fg cursor-help outline-none"
      />
      <span
        role="tooltip"
        className={`invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 transition-opacity absolute ${popoverPlacement} z-50 w-64 max-w-xs p-3 text-xs text-tm-fg bg-tm-bg-2 border border-tm-rule rounded shadow-lg whitespace-pre-line pointer-events-none`}
      >
        {content}
      </span>
    </span>
  );
}
