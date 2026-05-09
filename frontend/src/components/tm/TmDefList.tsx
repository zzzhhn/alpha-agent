"use client";

/**
 * TmDefList — workstation-style 2-column definition list.
 *
 * Used for data-dictionary panes (Data screen schema, Methodology
 * formulas, etc.). Renders as a CSS grid with a 140px label column +
 * 1fr value column, separated by 1px bg-tm-rule rules between every
 * cell — producing the design's `.tm-defs` "hairline-grid" look
 * without the cells needing explicit borders.
 */

import { type ReactNode } from "react";
import clsx from "clsx";

interface TmDefListProps {
  readonly children: ReactNode;
  readonly className?: string;
  /** Width of the label column. Default 140px matches the design CSS. */
  readonly dtWidth?: string;
}

export function TmDefList({ children, className, dtWidth }: TmDefListProps) {
  return (
    <dl
      className={clsx(
        "grid gap-px bg-tm-rule p-px font-tm-mono text-[11.5px]",
        className,
      )}
      style={{ gridTemplateColumns: `${dtWidth ?? "140px"} 1fr` }}
    >
      {children}
    </dl>
  );
}

interface TmDefProps {
  readonly term: ReactNode;
  readonly children: ReactNode;
  /** Render the value with mono + accent — for code-like definitions
   *  (factor expressions, formula glyphs). */
  readonly expr?: boolean;
}

export function TmDef({ term, children, expr = false }: TmDefProps) {
  // React.Fragment so dt + dd land as siblings under the parent dl grid.
  return (
    <>
      <dt className="bg-tm-bg-2 px-3 py-1.5 text-[10.5px] tracking-[0.04em] text-tm-muted">
        {term}
      </dt>
      <dd
        className={clsx(
          "m-0 bg-tm-bg px-3 py-1.5",
          expr ? "font-tm-mono text-tm-accent" : "text-tm-fg",
        )}
      >
        {children}
      </dd>
    </>
  );
}
