"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";

type Placement = "top" | "right" | "bottom" | "left";

interface TmTooltipProps {
  readonly children: ReactNode;
  readonly content: ReactNode;
  readonly placement?: Placement;
  readonly width?: number;
  readonly ariaLabel?: string;
  readonly className?: string;
}

const VIEWPORT_GAP = 8;
const TRIGGER_GAP = 6;

/** Canonical tooltip with viewport-clamped portal positioning. */
export function TmTooltip({
  children,
  content,
  placement = "bottom",
  width = 240,
  ariaLabel,
  className,
}: TmTooltipProps) {
  const tooltipId = useId();
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const place = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger || typeof window === "undefined") return;
    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltipRef.current?.getBoundingClientRect();
    const tooltipWidth = tooltipRect?.width || width;
    const tooltipHeight = tooltipRect?.height || 72;

    const centeredLeft = triggerRect.left + triggerRect.width / 2 - tooltipWidth / 2;
    const centeredTop = triggerRect.top + triggerRect.height / 2 - tooltipHeight / 2;
    const candidates: Record<Placement, { top: number; left: number }> = {
      top: { top: triggerRect.top - tooltipHeight - TRIGGER_GAP, left: centeredLeft },
      right: { top: centeredTop, left: triggerRect.right + TRIGGER_GAP },
      bottom: { top: triggerRect.bottom + TRIGGER_GAP, left: centeredLeft },
      left: { top: centeredTop, left: triggerRect.left - tooltipWidth - TRIGGER_GAP },
    };
    const preferred = candidates[placement];
    setPosition({
      top: Math.min(
        Math.max(preferred.top, VIEWPORT_GAP),
        window.innerHeight - tooltipHeight - VIEWPORT_GAP,
      ),
      left: Math.min(
        Math.max(preferred.left, VIEWPORT_GAP),
        window.innerWidth - tooltipWidth - VIEWPORT_GAP,
      ),
    });
  }, [placement, width]);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, place]);

  return (
    <span
      ref={triggerRef}
      tabIndex={0}
      aria-label={ariaLabel}
      aria-describedby={open ? tooltipId : undefined}
      className={clsx("inline-flex items-center", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      {children}
      {open
        ? createPortal(
            <span
              ref={tooltipRef}
              id={tooltipId}
              role="tooltip"
              style={{ position: "fixed", top: position.top, left: position.left, width }}
              className="pointer-events-none z-[1000] whitespace-pre-line rounded-[2px] border border-tm-rule-2 bg-tm-bg-2 p-2 font-sans text-[10.5px] leading-5 text-tm-fg shadow-lg"
            >
              {content}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
