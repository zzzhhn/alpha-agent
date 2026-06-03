"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * HoverTip - wraps a trigger and reveals a tooltip instantly on hover/focus.
 *
 * Renders the tooltip into a PORTAL on document.body with `position: fixed`,
 * positioned from the trigger's bounding rect and CLAMPED to the viewport.
 * This is the durable fix for the recurring "tooltip clipped by the sidebar /
 * table / pane" bug: an absolutely-positioned tooltip inside any ancestor with
 * `overflow: hidden|auto|scroll` gets cut off. A viewport-fixed portal has no
 * clipping ancestor, and the left-clamp keeps it on screen even when the
 * trigger sits hard against the left rail.
 *
 * Instant (no native-title ~1s delay): shown on the mouseenter/focus event.
 * `pointer-events-none` so it never traps the mouse. `content` supports `\n`.
 */
export function HoverTip({
  children,
  content,
  placement = "bottom",
  width = 224,
  className = "",
}: {
  children: ReactNode;
  content: string;
  placement?: "bottom" | "top";
  width?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(
    null,
  );

  const show = useCallback(() => {
    const el = ref.current;
    if (!el || typeof window === "undefined") return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const estH = 72; // rough; only used to decide flip near the bottom edge
    // Horizontal: center on the trigger, then clamp inside the viewport so a
    // left-rail-adjacent trigger never bleeds under the sidebar.
    const rawLeft = r.left + r.width / 2 - width / 2;
    const left = Math.max(
      margin,
      Math.min(rawLeft, window.innerWidth - width - margin),
    );
    // Vertical: requested side, but flip if it would overflow that edge.
    const wantsBelow = placement === "bottom";
    const below = r.bottom + 6;
    const above = r.top - estH - 6;
    const top =
      wantsBelow && below + estH <= window.innerHeight
        ? below
        : !wantsBelow && above >= margin
          ? above
          : wantsBelow
            ? Math.max(margin, above)
            : below;
    setCoords({ top, left });
  }, [placement, width]);

  const hide = useCallback(() => setCoords(null), []);

  return (
    <span
      ref={ref}
      className={`inline-flex items-center ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      {coords !== null
        ? createPortal(
            <span
              role="tooltip"
              style={{ position: "fixed", top: coords.top, left: coords.left, width }}
              className="pointer-events-none z-[1000] rounded border border-tm-rule bg-tm-bg-2 p-2 text-[11px] leading-snug text-tm-fg shadow-lg whitespace-pre-line"
            >
              {content}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
