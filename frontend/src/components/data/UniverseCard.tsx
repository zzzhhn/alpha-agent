"use client";

/**
 * Data-page composition primitives — UniverseOverview + UniverseTickers.
 *
 * The /data page wraps these two in a `<TmCols2>` so they sit side-by-
 * side in fixed-height "tabs" that scroll internally — neither pane
 * grows when its content does (e.g. user expands all sectors), they
 * just scroll. This keeps left and right vertically aligned regardless
 * of how either side's content changes.
 *
 * UniverseOverview merges the legacy UNIVERSE pane + DATA.COVERAGE pane
 * into one. The 5-cell KPI strip carries the union of their stats. Then
 * a collapsible 3-row category summary (`COVERAGE.CATEGORIES`) replaces
 * the prior wall of ~20 per-field fill-rate bars: each row shows the
 * category's average fill rate; click ▸ to expand and reveal the field-
 * level bars that were dominating the page before. Worst-coverage
 * tickers also moved into a collapsible block (closed by default).
 *
 * UniverseTickers is the sectorised ticker roster. Each GICS sector is
 * its own collapsible block; the body inside each block is a fixed-
 * density grid (78px-min auto-fill) so symbol density is predictable
 * regardless of the longest ticker in the bucket. When a sector
 * expands, the pane scrolls — it does NOT grow vertically, so the
 * paired UniverseOverview pane stays the same height.
 *
 * `UniverseDetail` and `UniverseCard` are kept as back-compat aliases
 * — old call sites continue to render the same content (overview +
 * tickers stacked, no fixed height).
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
// equivalents yet.
function colorFor(rate: number): string {
  if (rate >= 0.99) return "var(--tm-pos)";
  if (rate >= 0.95) return "#84cc16"; // lime
  if (rate >= 0.85) return "var(--tm-warn)";
  if (rate >= 0.7) return "#f97316"; // orange
  return "var(--tm-neg)";
}

// Fill-height pane CSS — TmPane root takes the full grid-cell height,
// the body wrapper grows to fill remaining space and scrolls when
// content overflows. Used by both panes inside data/page.tsx's TmCols2.
const FILL_PANE_CLASS = "h-full overflow-hidden";
const FILL_BODY_CLASS = "flex-1 min-h-0 overflow-y-auto";

// ── UniverseOverview ────────────────────────────────────────────────

interface UniverseOverviewProps {
  readonly universe: UniverseInfo;
  /** Coverage payload (from `fetchCoverage`). When undefined, the pane
   *  renders without the fill-rate bars / worst-tickers section. */
  readonly coverage?: CoverageResponse | null;
  /** When true, the pane fills its parent's height and scrolls
   *  internally on overflow. Used by data/page.tsx's TmCols2 to make
   *  Overview + Tickers panes the same height. Defaults to false so
   *  the back-compat `UniverseDetail` keeps its auto-height layout. */
  readonly fillHeight?: boolean;
}

export function UniverseOverview({
  universe,
  coverage,
  fillHeight = false,
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
      className={fillHeight ? FILL_PANE_CLASS : undefined}
      bodyClassName={fillHeight ? FILL_BODY_CLASS : undefined}
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

      {/* Coverage drilldown — collapsible category rows. Replaces the
          previous wall of ~20 per-field fill-rate bars, which was both
          information overload and the cause of the height mismatch
          with the right pane. */}
      {coverage && (
        <section className="border-t border-tm-rule">
          <div className="px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted">
            {t(locale, "data.coverage.title")}
          </div>
          <div className="flex flex-col">
            {(["ohlcv", "metadata", "fundamental"] as const).map((cat) => {
              const fields = byCategory.get(cat);
              if (!fields || fields.length === 0) return null;
              return (
                <CategoryRow
                  key={cat}
                  label={t(locale, CATEGORY_LABEL_KEY[cat])}
                  fields={fields}
                />
              );
            })}
          </div>
        </section>
      )}

      {/* Worst-tickers — collapsible block (closed by default). Was a
          full-width section taking ~80px; now hidden behind a single
          row that the user expands when they actually want this view. */}
      {coverage && worstTickers.length > 0 && (
        <Collapsible
          label={t(locale, "data.coverage.worstTickers")}
          summary={`${worstTickers.length} below 100%`}
          tone="warn"
        >
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
        </Collapsible>
      )}

      {coverage && (
        <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
          {t(locale, "data.coverage.legend")}
        </p>
      )}
    </TmPane>
  );
}

// ── CategoryRow — collapsible per-category coverage summary ─────────

function mean(rates: readonly number[]): number {
  if (rates.length === 0) return 0;
  return rates.reduce((s, r) => s + r, 0) / rates.length;
}

function CategoryRow({
  label,
  fields,
}: {
  label: string;
  fields: readonly FieldCoverage[];
}) {
  const [open, setOpen] = useState(false);
  const avg = mean(fields.map((f) => f.fill_rate));
  const healthy = fields.filter((f) => f.fill_rate >= 0.99).length;
  const tone = colorFor(avg);

  return (
    <div className="border-t border-tm-rule first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-1.5 text-left font-tm-mono text-[11px] transition-colors hover:bg-tm-bg-2"
        aria-expanded={open}
      >
        <span className="w-3 text-tm-muted" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="w-32 truncate font-semibold uppercase tracking-[0.04em] text-tm-accent">
          {label}
        </span>
        <span className="w-32 text-tm-muted">
          {healthy}/{fields.length} healthy
        </span>
        {/* Mini summary bar — same colour ramp as field-level bars */}
        <div className="relative h-2.5 flex-1 overflow-hidden bg-tm-bg-3">
          <div
            className="h-full transition-[width] duration-200"
            style={{ width: `${avg * 100}%`, background: tone }}
          />
        </div>
        <span className="w-14 text-right tabular-nums text-tm-fg">
          {(avg * 100).toFixed(2)}%
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-1 bg-tm-bg-2 px-3 py-2">
          {fields.map((f) => (
            <FieldBar key={f.name} field={f} />
          ))}
        </div>
      )}
    </div>
  );
}

function FieldBar({ field }: { field: FieldCoverage }) {
  return (
    <div className="flex items-center gap-3 font-tm-mono text-[11px]">
      <code className="w-32 truncate text-tm-fg" title={field.name}>
        {field.name}
      </code>
      <div className="relative h-2.5 flex-1 overflow-hidden bg-tm-bg-3">
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
      <span className="w-20 text-right text-[10px] text-tm-muted">
        {field.n_present.toLocaleString()} / {field.n_total.toLocaleString()}
      </span>
    </div>
  );
}

// ── Generic Collapsible (used for worst-tickers + future drilldowns) ─

function Collapsible({
  label,
  summary,
  tone,
  defaultOpen = false,
  children,
}: {
  label: string;
  summary?: string;
  tone?: "warn" | "pos" | "muted";
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const summaryTone =
    tone === "warn"
      ? "text-tm-warn"
      : tone === "pos"
        ? "text-tm-pos"
        : "text-tm-muted";
  return (
    <div className="border-t border-tm-rule">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-1.5 text-left font-tm-mono text-[10px] uppercase tracking-[0.08em] transition-colors hover:bg-tm-bg-2"
        aria-expanded={open}
      >
        <span className="w-3 text-tm-muted" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="font-semibold text-tm-fg-2">{label}</span>
        {summary && <span className={summaryTone}>· {summary}</span>}
      </button>
      {open && children}
    </div>
  );
}

// ── UniverseTickers (sectorised, fill-height capable) ───────────────

interface UniverseTickersProps {
  readonly universe: UniverseInfo;
  /** When true, the pane fills its parent's height and scrolls
   *  internally on overflow. Same convention as UniverseOverview. */
  readonly fillHeight?: boolean;
}

interface SectorBucket {
  readonly key: string;
  readonly label: string;
  readonly tickers: readonly string[];
}

const UNKNOWN_SECTOR = "Unknown";
// Sectors smaller than this stay open by default; bigger ones collapse.
const COLLAPSE_THRESHOLD = 24;

function bucketTickers(universe: UniverseInfo): SectorBucket[] {
  const sectors = universe.sectors;
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

export function UniverseTickers({
  universe,
  fillHeight = false,
}: UniverseTickersProps) {
  const buckets = useMemo(() => bucketTickers(universe), [universe]);

  return (
    <TmPane
      title={`TICKERS.${universe.id}`}
      meta={
        <span className="font-tm-mono">
          {universe.tickers.length} symbols · {buckets.length} sectors
        </span>
      }
      className={fillHeight ? FILL_PANE_CLASS : undefined}
      bodyClassName={fillHeight ? FILL_BODY_CLASS : undefined}
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

/** Legacy combined renderer — overview + tickers stacked vertically,
 *  auto-height (no fill behavior). */
export function UniverseDetail({ universe, coverage }: UniverseDetailProps) {
  return (
    <>
      <UniverseOverview universe={universe} coverage={coverage} />
      <UniverseTickers universe={universe} />
    </>
  );
}

export const UniverseCard = UniverseDetail;
