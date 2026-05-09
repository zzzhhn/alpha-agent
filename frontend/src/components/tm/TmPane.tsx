"use client";

/**
 * TmPane + TmScreen — workstation layout primitives (Variation C).
 *
 * `TmScreen` is the page-level container. It establishes the
 * "workstation floor" (`bg-tm-bg`) so trailing space below the last
 * pane reads as continuous floor rather than as an unfilled grid cell.
 * Children stack vertically with no gap; each pane brings its own
 * `border-bottom` hairline that separates it from the next.
 *
 * `TmPane` is a flat content section. Unlike the legacy rounded-card
 * pattern, panes have NO outer border; the `border-b border-tm-rule`
 * comes from the parent screen's child selector (or an explicit prop
 * for cases where the pane stands alone). Header is the only thing
 * with an explicit border-bottom — it always separates from the body.
 *
 * Two-col side-by-side panes use the sibling `<TmCols2>` container,
 * which divides space with a single internal `border-r` hairline.
 *
 * Source of truth: styles-screens.css `.tm-screen / .tm-pane / .tm-cols-2`.
 */

import { type ReactNode } from "react";
import clsx from "clsx";

interface TmScreenProps {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmScreen({ children, className }: TmScreenProps) {
  return (
    <div
      className={clsx(
        "flex h-full min-h-0 min-w-0 flex-col bg-tm-bg",
        // Each direct pane child contributes its own bottom hairline so
        // the workstation floor (the empty area below the last pane) is
        // continuous, not boxed.
        "[&>*:not(:last-child)]:border-b [&>*:not(:last-child)]:border-tm-rule",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TmPaneProps {
  readonly title?: ReactNode;
  readonly meta?: ReactNode;
  readonly children?: ReactNode;
  readonly className?: string;
  readonly bodyClassName?: string;
  /** When true, the pane gets its own outer border (for use OUTSIDE a
   *  TmScreen — e.g. a standalone modal or a centred config panel). The
   *  default false is what every screen uses. */
  readonly standalone?: boolean;
}

export function TmPane({
  title,
  meta,
  children,
  className,
  bodyClassName,
  standalone = false,
}: TmPaneProps) {
  return (
    <section
      className={clsx(
        "flex flex-col bg-tm-bg",
        standalone && "border border-tm-rule",
        className,
      )}
    >
      {(title || meta) && (
        <header className="flex items-center justify-between gap-3 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10.5px]">
          <span className="font-semibold uppercase tracking-[0.06em] text-tm-accent">
            {title}
          </span>
          {meta && (
            <span className="tracking-[0.02em] text-tm-muted">{meta}</span>
          )}
        </header>
      )}
      {children !== undefined && children !== null && (
        <div className={clsx("flex flex-col", bodyClassName)}>{children}</div>
      )}
    </section>
  );
}

interface TmCols2Props {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmCols2({ children, className }: TmCols2Props) {
  return (
    <div
      className={clsx(
        "grid grid-cols-2 bg-tm-bg",
        // Internal hairline between the two pane children — last child
        // has no right border so it doesn't double-up against the
        // screen's outer chrome.
        "[&>*:not(:last-child)]:border-r [&>*:not(:last-child)]:border-tm-rule",
        className,
      )}
    >
      {children}
    </div>
  );
}
