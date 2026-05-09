"use client";

/**
 * Universe detail panes — replaces the legacy "grid of UniverseCards"
 * with a single edge-to-edge `UNIVERSE.{id}` pane (containing a 6-cell
 * KPI strip) followed by a flush ticker-roster pane. The page selects
 * which universe is rendered via tm-subbar chips.
 *
 * Exports:
 *   UniverseDetail — the active universe rendered as 1-2 panes
 *   UniverseCard   — back-compat alias (still default-exports the same)
 */

import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { UniverseInfo } from "@/lib/types";

interface UniverseDetailProps {
  readonly universe: UniverseInfo;
}

export function UniverseDetail({ universe }: UniverseDetailProps) {
  const { locale } = useLocale();
  return (
    <>
      <TmPane
        title={`UNIVERSE.${universe.id}`}
        meta={
          <span className="font-tm-mono">
            benchmark = {universe.benchmark} · {universe.currency}
          </span>
        }
      >
        <TmKpiGrid>
          <TmKpi
            label={t(locale, "data.universe.tickerCount")}
            value={universe.ticker_count.toLocaleString()}
            sub="survivorship-corrected"
          />
          <TmKpi
            label={t(locale, "data.universe.days")}
            value={universe.n_days.toLocaleString()}
            sub={`${universe.start_date} → ${universe.end_date}`}
          />
          <TmKpi
            label={t(locale, "data.universe.benchmark")}
            value={universe.benchmark}
          />
          <TmKpi
            label="CURRENCY"
            value={universe.currency}
            sub="adjusted for splits & div"
          />
          <TmKpi
            label={t(locale, "data.universe.range")}
            value={universe.start_date}
            sub={`→ ${universe.end_date}`}
          />
          <TmKpi
            label="UNIVERSE.ID"
            value={universe.id}
            sub={universe.name}
          />
        </TmKpiGrid>
      </TmPane>

      <TmPane
        title={`TICKERS.${universe.id}`}
        meta={
          <span className="font-tm-mono">
            {universe.tickers.length} symbols
          </span>
        }
      >
        <div className="flex flex-wrap gap-1 px-3 py-2.5">
          {universe.tickers.map((tk) => (
            <span
              key={tk}
              className="border border-tm-rule bg-tm-bg-2 px-1.5 py-px font-tm-mono text-[10.5px] text-tm-fg-2"
            >
              {tk}
            </span>
          ))}
        </div>
      </TmPane>
    </>
  );
}

// Back-compat: any caller still importing `UniverseCard` gets the same.
export const UniverseCard = UniverseDetail;
