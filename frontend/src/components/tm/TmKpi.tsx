"use client";

/**
 * TmKpi + TmKpiGrid — workstation metric cells.
 *
 * The grid is auto-fit columns at 140px min so any number of KPIs
 * lays out without manual sizing. Cells are separated by 1px
 * background-as-rule (gap-px on a tm-rule background).
 *
 * Each cell is strictly 3 lines:
 *   - 9.5px uppercase muted label   (`tm-kpi-k`)
 *   - 18px tabular-num value        (`tm-kpi-v` + optional .pos/.neg/.warn tone)
 *   - 10px tabular-num caption      (`tm-kpi-sub`) — optional
 *
 * Mirrors styles-screens.css `.tm-kpis / .tm-kpi`.
 */

import { type ReactNode } from "react";
import clsx from "clsx";

interface TmKpiGridProps {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmKpiGrid({ children, className }: TmKpiGridProps) {
  return (
    <div
      className={clsx(
        // gap-px against bg-tm-rule produces the design's hairline
        // between cells without breaking auto-fit reflow.
        "grid gap-px bg-tm-rule",
        // auto-fit min 140px = match `.tm-kpis` repeat behavior
        "[grid-template-columns:repeat(auto-fit,minmax(140px,1fr))]",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TmKpiProps {
  readonly label: ReactNode;
  readonly value: ReactNode;
  readonly sub?: ReactNode;
  readonly tone?: "default" | "pos" | "neg" | "warn";
  readonly className?: string;
}

export function TmKpi({
  label,
  value,
  sub,
  tone = "default",
  className,
}: TmKpiProps) {
  const valueTone =
    tone === "pos"
      ? "text-tm-pos"
      : tone === "neg"
        ? "text-tm-neg"
        : tone === "warn"
          ? "text-tm-warn"
          : "text-tm-fg";
  return (
    <div
      className={clsx(
        "flex min-w-0 flex-col bg-tm-bg px-3 py-2 font-tm-mono",
        className,
      )}
    >
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </div>
      <div
        className={clsx(
          "mt-0.5 truncate text-[18px] tabular-nums",
          valueTone,
        )}
      >
        {value}
      </div>
      {sub !== undefined && sub !== null && (
        <div className="mt-0.5 truncate text-[10px] tabular-nums text-tm-muted">
          {sub}
        </div>
      )}
    </div>
  );
}
