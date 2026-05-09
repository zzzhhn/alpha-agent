"use client";

import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { UniverseInfo } from "@/lib/types";

interface UniverseCardProps {
  readonly universe: UniverseInfo;
}

/**
 * UniverseCard — one universe rendered as a workstation pane.
 *
 * Header row carries id + currency tag (replaces the prior Linear-style
 * purple badge). Body is a 2-col stat grid plus an expandable ticker
 * roster. All copy keys preserved.
 */
export function UniverseCard({ universe }: UniverseCardProps) {
  const { locale } = useLocale();
  return (
    <TmPane
      title={universe.name}
      meta={
        <span className="font-tm-mono">
          {universe.id} · {universe.currency}
        </span>
      }
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-3 py-3 font-tm-mono text-[12px] md:grid-cols-4">
        <Stat
          label={t(locale, "data.universe.tickerCount")}
          value={universe.ticker_count.toString()}
        />
        <Stat
          label={t(locale, "data.universe.benchmark")}
          value={universe.benchmark}
        />
        <Stat
          label={t(locale, "data.universe.days")}
          value={universe.n_days.toString()}
        />
        <Stat
          label={t(locale, "data.universe.range")}
          value={`${universe.start_date} → ${universe.end_date}`}
        />
      </dl>

      <details className="border-t border-tm-rule">
        <summary className="cursor-pointer px-3 py-2 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-muted hover:text-tm-fg">
          {t(locale, "data.universe.tickersLabel")} ({universe.tickers.length})
        </summary>
        <div className="flex flex-wrap gap-1 px-3 pb-3 pt-1">
          {universe.tickers.map((tk) => (
            <span
              key={tk}
              className="border border-tm-rule bg-tm-bg-3 px-1.5 py-0.5 font-tm-mono text-[11px] text-tm-fg-2"
            >
              {tk}
            </span>
          ))}
        </div>
      </details>
    </TmPane>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
        {label}
      </dt>
      <dd className="tabular-nums text-tm-fg">{value}</dd>
    </div>
  );
}
