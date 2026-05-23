"use client";

/**
 * GroupAccordion — reusable accordion shell for /backtest redesign (T6).
 *
 * One row per analytics group (RISK DETAIL / REGIME BREAKDOWN / HOLDINGS /
 * OPERATIONS). Closed state shows a single compact header with title,
 * sub-pane count, and an optional ⚠ severity badge. Open state reveals
 * stacked sub-panes below.
 *
 * Per spec §7 the four groups together host nine sub-pane wrappers. The
 * orchestrator (`BacktestAnalyticsGroups`) decides which children render
 * inside each accordion and supplies the badge.
 *
 * Visual chrome borrows from the /alpha AnalyticsAccordion precedent
 * (font-tm-mono, tm-* tokens) but renders a full bordered card because
 * a /backtest group is a top-level container, not an inline disclosure.
 */

import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

export type GroupBadgeSeverity = "warn" | "alert";

export interface GroupBadge {
  readonly severity: GroupBadgeSeverity;
  readonly reason: string;
}

interface Props {
  readonly title: string;
  readonly count: number;
  readonly badge?: GroupBadge | null;
  readonly defaultOpen?: boolean;
  readonly children: ReactNode;
}

export function GroupAccordion({
  title,
  count,
  badge,
  defaultOpen = false,
  children,
}: Props) {
  const { locale } = useLocale();
  const [open, setOpen] = useState<boolean>(defaultOpen);

  const countLabel = t(locale, "backtest.group.showN" as Parameters<typeof t>[1]).replace(
    "{n}",
    String(count),
  );
  const hideLabel = t(locale, "backtest.group.hideN" as Parameters<typeof t>[1]);

  const badgeToneClass =
    badge?.severity === "alert" ? "text-tm-neg" : "text-tm-warn";

  return (
    <section className="flex flex-col rounded border border-tm-rule bg-tm-bg">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 border-b border-tm-rule bg-tm-bg-2 px-3 py-2 font-tm-mono text-[10.5px] hover:bg-tm-bg-3"
      >
        <span className="flex items-center gap-2">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-tm-muted" strokeWidth={1.75} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-tm-muted" strokeWidth={1.75} />
          )}
          <span className="font-semibold uppercase tracking-[0.06em] text-tm-accent">
            {title}
          </span>
          <span className="text-tm-muted">· {open ? hideLabel : countLabel}</span>
          {badge ? (
            <span
              title={badge.reason}
              className={`ml-1 inline-flex items-center gap-1 ${badgeToneClass}`}
            >
              <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span className="text-[10px] uppercase tracking-[0.04em]">
                {badge.reason}
              </span>
            </span>
          ) : null}
        </span>
      </button>
      {open ? (
        <div className="flex flex-col gap-3 bg-tm-bg p-3">{children}</div>
      ) : null}
    </section>
  );
}
