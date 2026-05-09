"use client";

/**
 * TmPane — workstation-aesthetic content pane.
 *
 * The bread-and-butter container for every page in Variation C. A pane
 * is a flat hairline-bordered region with a thin header bar containing
 * an accent-coloured title and optional muted meta text. The pane body
 * has no inner padding by default so callers can choose between a
 * padded form layout, a flush table, or a flush metric grid.
 *
 * The visual translates the .tm-pane / .tm-pane-head pattern from the
 * design's styles-terminal.css into Tailwind utilities + the project's
 * extended `tm-*` colour namespace (tailwind.config.ts).
 */

import { type ReactNode } from "react";
import clsx from "clsx";

interface TmPaneProps {
  readonly title?: ReactNode;
  readonly meta?: ReactNode;
  readonly children: ReactNode;
  readonly className?: string;
  readonly bodyClassName?: string;
}

export function TmPane({
  title,
  meta,
  children,
  className,
  bodyClassName,
}: TmPaneProps) {
  return (
    <section
      className={clsx(
        "flex flex-col border border-tm-rule bg-tm-bg",
        className,
      )}
    >
      {(title || meta) && (
        <header className="flex items-center justify-between border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10.5px]">
          <span className="font-semibold uppercase tracking-[0.06em] text-tm-accent">
            {title}
          </span>
          {meta && (
            <span className="tracking-[0.02em] text-tm-muted">{meta}</span>
          )}
        </header>
      )}
      <div className={clsx("flex flex-col", bodyClassName)}>{children}</div>
    </section>
  );
}
