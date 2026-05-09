"use client";

/**
 * Data-page composition primitives — UniverseOverview + UniverseTickers.
 *
 * The /data page wraps these two in a `<TmCols2>` so they sit side-by-
 * side, saving the vertical real estate the previous "stack everything
 * full-width" layout wasted.
 *
 * UniverseOverview merges the legacy UNIVERSE pane + DATA.COVERAGE pane
 * into one. The 5-cell KPI strip carries the union of their stats
 * (ticker count, trading days, OHLCV %, benchmark+currency, universe
 * id). Below the strip, when coverage data is present, the per-field
 * fill-rate bars + worst-coverage tickers list render in the same pane
 * — what was a separate DATA.COVERAGE pane below.
 *
 * UniverseTickers is the sectorised ticker roster. Each GICS sector is
 * its own collapsible block; the body inside each block is a fixed-
 * density grid (78px-min auto-fill) so symbol density is predictable
 * regardless of the longest ticker in the bucket.
 *
 * `UniverseDetail` and `UniverseCard` are kept as back-compat aliases
 * — old call sites continue to render the same content (overview +
 * tickers stacked).
 */

import { useMemo, useState } from "react";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type {
  UniverseInfo,
  CoverageResponse,
  FieldCoverage,
} from "@/lib/types";

const CATEGORY_LABEL_KEY = {
  ohlcv: "data.coverage.catOhlcv",
  metadata: "data.coverage.catMetadata",
  fundamental: "data.coverage.catFundamental",
} as const;

// Coverage health colour ramp — tokens for accent/warn/neg, hex
// fallbacks for the lime/orange middle steps that don't have palette
// equivalents yet. Same ramp as the legacy CoverageOverview.
function colorFor(rate: number): string {
  if (rate >= 0.99) return "var(--tm-pos)";
  if (rate >= 0.95) return "#84cc16"; // lime
  if (rate >= 0.85) return "var(--tm-warn)";
  if (rate >= 0.7) return "#f97316"; // orange
  return "var(--tm-neg)";
}

// ── UniverseOverview ────────────────────────────────────────────────

interface UniverseOverviewProps {
  readonly universe: UniverseInfo;
  /** Coverage payload (from `fetchCoverage`). When undefined, the pane
   *  renders without the fill-rate bars / worst-tickers section. */
  readonly coverage?: CoverageResponse | null;
}

export function UniverseOverview({
  universe,
  coverage,
}: UniverseOverviewProps) {
  const { locale } = useLocale();

  const byCategory = useMemo(() => {
    const map = new Map<string, FieldCoverage[]>();
    if (!coverage) return map;
    for (const f of coverage.field_coverage) {
      if (!map.has(f.category)) map.set(f.category, []);
      map.get(f.category)!.push(f);
    }
    return map;
  }, [coverage]);

  const worstTickers = useMemo(() => {
    if (!coverage) return [] as CoverageResponse["ticker_coverage"];
    return coverage.ticker_coverage
      .slice(0, 6)
      .filter((tk) => tk.fill_rate < 1.0);
  }, [coverage]);

  return (
    <TmPane
      title={`UNIVERSE.${universe.id}`}
      meta={
        <span className="font-tm-mono">
          benchmark = {universe.benchmark} · {universe.currency}
        </span>
      }
    >
      {/* Merged KPI strip — 5 cells consolidate the previous UNIVERSE
          + COVERAGE overlap (tickers, days, ohlcv%, range, benchmark) */}
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
          label={t(locale, "data.coverage.kOhlcvPct")}
          value={
            coverage ? `${coverage.ohlcv_coverage_pct.toFixed(2)}%` : "—"
          }
          tone={
            coverage && coverage.ohlcv_coverage_pct >= 99
              ? "pos"
              : coverage
                ? "warn"
                : "default"
          }
          sub="missing bars forward-filled"
        />
        <TmKpi
          label={t(locale, "data.universe.benchmark")}
          value={universe.benchmark}
          sub={universe.currency}
        />
        <TmKpi
          label="UNIVERSE.ID"
          value={universe.id}
          sub={universe.name}
        />
      </TmKpiGrid>

      {/* Per-field fill rate bars, grouped by category — pulled in from
          the legacy CoverageOverview pane. Renders only when coverage
          data has loaded. */}
      {coverage && (
        <>
          {(["ohlcv", "metadata", "fundamental"] as const).map((cat) => {
            const fields = byCategory.get(cat);
            if (!fields || fields.length === 0) return null;
            return (
              <section key={cat} className="border-t border-tm-rule">
                <div className="px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted">
                  {t(locale, CATEGORY_LABEL_KEY[cat])} ({fields.length})
                </div>
                <div className="flex flex-col gap-1 px-3 pb-2">
                  {fields.map((f) => (
                    <FieldBar key={f.name} field={f} />
                  ))}
                </div>
              </section>
            );
          })}

          {worstTickers.length > 0 && (
            <section className="border-t border-tm-rule">
              <div className="px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted">
                {t(locale, "data.coverage.worstTickers")}
              </div>
              <div className="flex flex-col gap-1 px-3 pb-2 font-tm-mono">
                {worstTickers.map((tk) => (
                  <div
                    key={tk.ticker}
                    className="flex items-center gap-3 text-[11px]"
                  >
                    <span className="w-20 font-semibold text-tm-fg">
                      {tk.ticker}
                    </span>
                    <div className="relative h-2.5 flex-1 overflow-hidden bg-tm-bg-3">
                      <div
                        className="h-full"
                        style={{
                          width: `${tk.fill_rate * 100}%`,
                          background: colorFor(tk.fill_rate),
                        }}
                      />
                    </div>
                    <span className="w-14 text-right tabular-nums text-tm-fg">
                      {(tk.fill_rate * 100).toFixed(1)}%
                    </span>
                    <span className="w-20 text-right text-[10px] text-tm-muted">
                      {tk.n_missing} missing
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
            {t(locale, "data.coverage.legend")}
          </p>
        </>
      )}
    </TmPane>
  );
}

function FieldBar({ field }: { field: FieldCoverage }) {
  return (
    <div className="flex items-center gap-3 font-tm-mono text-[11px]">
      <code className="w-44 truncate text-tm-fg" title={field.name}>
        {field.name}
      </code>
      <div className="relative h-3 flex-1 overflow-hidden bg-tm-bg-3">
        <div
          className="h-full transition-[width] duration-200"
          style={{
            width: `${field.fill_rate * 100}%`,
            background: colorFor(field.fill_rate),
          }}
        />
      </div>
      <span className="w-14 text-right tabular-nums text-tm-fg">
        {(field.fill_rate * 100).toFixed(1)}%
      </span>
      <span className="w-24 text-right text-[10px] text-tm-muted">
        {field.n_present.toLocaleString()} / {field.n_total.toLocaleString()}
      </span>
    </div>
  );
}

// ── UniverseTickers (sectorised) ────────────────────────────────────

interface UniverseTickersProps {
  readonly universe: UniverseInfo;
}

interface SectorBucket {
  readonly key: string;
  readonly label: string;
  readonly tickers: readonly string[];
}

const UNKNOWN_SECTOR = "Unknown";
// Sectors smaller than this stay open by default; bigger ones collapse
// so the pane doesn't scroll forever.
const COLLAPSE_THRESHOLD = 24;

function bucketTickers(universe: UniverseInfo): SectorBucket[] {
  const sectors = universe.sectors;
  // No sector data → single bucket containing every ticker. This is
  // what fires when (a) the backend predates the `sectors` field, or
  // (b) the loaded panel has no sector column. The fallback keeps the
  // pane functional.
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

  // Stable order: largest bucket first, "Unknown" pinned to the bottom.
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

export function UniverseTickers({ universe }: UniverseTickersProps) {
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
          <SectorBlock key={b.key} bucket={b} isFirst={idx === 0} />
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
        <span className="w-3 text-tm-muted" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="font-semibold text-tm-accent">{bucket.label}</span>
        <span className="text-tm-muted">· {bucket.tickers.length}</span>
      </button>
      {open && (
        <div
          className="grid gap-px bg-tm-rule p-px"
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

// ── Back-compat exports ─────────────────────────────────────────────

interface UniverseDetailProps {
  readonly universe: UniverseInfo;
  readonly coverage?: CoverageResponse | null;
}

/** Legacy combined renderer — overview + tickers stacked vertically.
 *  Retained so any caller that still imports `UniverseDetail` /
 *  `UniverseCard` keeps working. New callers should use
 *  `UniverseOverview` + `UniverseTickers` directly inside a TmCols2. */
export function UniverseDetail({ universe, coverage }: UniverseDetailProps) {
  return (
    <>
      <UniverseOverview universe={universe} coverage={coverage} />
      <UniverseTickers universe={universe} />
    </>
  );
}

export const UniverseCard = UniverseDetail;
