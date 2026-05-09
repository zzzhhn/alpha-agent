"use client";

/**
 * Universe detail panes — UNIVERSE.{id} KPI strip + a sectorised
 * TICKERS pane.
 *
 * The TICKERS pane is split into one collapsible block per sector
 * (GICS-1) instead of a wall of chip soup. Each sector header line
 * shows: sector name + ticker count + chevron, and the body of each
 * sector renders as a tight 6-7 column grid of ticker codes — fixed
 * column count (no flex-wrap chip flow) so density is predictable
 * regardless of name length.
 *
 * When the panel has no per-ticker sector mapping (e.g. legacy v1
 * panels, or backend predates the field), every ticker falls into a
 * single "All tickers" group and the pane reads identically to the
 * pre-sector version.
 */

import { useMemo, useState } from "react";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { UniverseInfo } from "@/lib/types";

interface UniverseDetailProps {
  readonly universe: UniverseInfo;
}

interface SectorBucket {
  readonly key: string;
  readonly label: string;
  readonly tickers: readonly string[];
}

const UNKNOWN_SECTOR = "Unknown";
// Initial-collapse threshold: sectors smaller than this stay open by
// default; larger sectors collapse so the pane doesn't scroll forever.
const COLLAPSE_THRESHOLD = 24;

function bucketTickers(universe: UniverseInfo): SectorBucket[] {
  const sectors = universe.sectors;
  // No sector data → single bucket containing every ticker.
  if (!sectors || sectors.length !== universe.tickers.length) {
    return [
      {
        key: "__all",
        label: "All tickers",
        tickers: universe.tickers,
      },
    ];
  }

  const map = new Map<string, string[]>();
  universe.tickers.forEach((tk, i) => {
    const sec = sectors[i] ?? UNKNOWN_SECTOR;
    const list = map.get(sec) ?? [];
    list.push(tk);
    map.set(sec, list);
  });

  // Stable order: largest sector first, "Unknown" pinned to the end.
  // `Array.from` instead of spread to keep the iteration target-safe
  // for our tsconfig (avoids the --downlevelIteration TS2802 error).
  return Array.from(map.entries())
    .sort(([aK, aTk], [bK, bTk]) => {
      if (aK === UNKNOWN_SECTOR) return 1;
      if (bK === UNKNOWN_SECTOR) return -1;
      return bTk.length - aTk.length;
    })
    .map(([sec, tickers]) => ({
      key: sec,
      label: sec,
      tickers,
    }));
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

      <SectorTickersPane universe={universe} />
    </>
  );
}

function SectorTickersPane({ universe }: UniverseDetailProps) {
  const buckets = useMemo(() => bucketTickers(universe), [universe]);

  return (
    <TmPane
      title={`TICKERS.${universe.id}`}
      meta={
        <span className="font-tm-mono">
          {universe.tickers.length} symbols · {buckets.length} sectors
        </span>
      }
    >
      <div className="flex flex-col">
        {buckets.map((b, idx) => (
          <SectorBlock
            key={b.key}
            bucket={b}
            isFirst={idx === 0}
          />
        ))}
      </div>
    </TmPane>
  );
}

function SectorBlock({
  bucket,
  isFirst,
}: {
  bucket: SectorBucket;
  isFirst: boolean;
}) {
  const initiallyOpen = bucket.tickers.length < COLLAPSE_THRESHOLD;
  const [open, setOpen] = useState(initiallyOpen);

  return (
    <div
      className={`flex flex-col ${isFirst ? "" : "border-t border-tm-rule"}`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 bg-tm-bg-2 px-3 py-1.5 text-left font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-fg-2 transition-colors hover:text-tm-fg"
        aria-expanded={open}
      >
        <span
          className="w-3 text-tm-muted"
          aria-hidden="true"
        >
          {open ? "▾" : "▸"}
        </span>
        <span className="font-semibold text-tm-accent">
          {bucket.label}
        </span>
        <span className="text-tm-muted">
          · {bucket.tickers.length}
        </span>
      </button>
      {open && (
        <div
          className="grid gap-px bg-tm-rule p-px"
          // Fixed-density grid: 7 columns at ≥1024px, 5 columns at md,
          // 4 on small. Predictable rhythm vs the prior wrap-anywhere
          // chip flow.
          style={{
            gridTemplateColumns: "repeat(auto-fill, minmax(78px, 1fr))",
          }}
        >
          {bucket.tickers.map((tk) => (
            <span
              key={tk}
              className="bg-tm-bg px-2 py-1 font-tm-mono text-[11px] text-tm-fg-2"
            >
              {tk}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Back-compat alias for any caller still importing UniverseCard.
export const UniverseCard = UniverseDetail;
