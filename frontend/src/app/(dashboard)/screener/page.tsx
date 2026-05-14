"use client";

/**
 * Screener page — workstation port v2 (Stage 3 · 6/9, density rework).
 *
 * Ships 7 density improvements over v1:
 *
 *   1. SECTORS as a chip multi-select (was free-text). Pulls live GICS-1
 *      list from /data/sectors at mount; selection state is a Set.
 *   2. Quick-preset chips on cap inputs (10B / 100B / 1T), as_of_date
 *      (today / -7d / -30d / -90d), and lookback (30 / 60 / 120 / 252).
 *   3. RECS.SECTORS / RECS.CAPMIX panes (TmCols2): horizontal bars
 *      breaking down top-N by sector and by cap quintile.
 *   4. CONCENTRATION pill in subbar — surfaces max-sector share so a
 *      "60% of top 20 are Tech" basket gets called out as sector beta
 *      rather than alpha.
 *   5. AGGREGATE.CONTRIBUTION pane — across the entire top-N basket,
 *      sum |contribution| by factor; the dominant factor jumps out as
 *      the longest bar. Helps detect "top 20 was driven by 1 factor".
 *   6. DIAGNOSTICS rows gain inline divergent IC bar + n_eligible
 *      proportion bar. Same data, visual weight.
 *   7. RESULTS KPI grid expands 4 → 6: adds N_UNIVERSE + ELIG_RATE
 *      (n_eligible / n_universe) so the eligibility funnel ratio is
 *      legible at a glance.
 *
 * Behavior preserved: PREFILL_KEY handoff, runScreener payload shape,
 * CSV export, expand-one-at-a-time, all existing inputs.
 */

import {
  Fragment,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
} from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import { useWatchlist } from "@/hooks/useWatchlist";
import WatchlistStar from "@/components/ui/WatchlistStar";
import {
  listZoo,
  readDirection,
  type ZooEntry,
  type ZooDirection,
} from "@/lib/factor-zoo";
import { runScreener, fetchSectors, fetchUniverses } from "@/lib/api";
import type {
  CombineMethod,
  ScreenerFactorInput,
  ScreenerResponse,
} from "@/lib/types";
import { TmScreen, TmPane, TmCols2 } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmStatusPill,
  TmChip,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput, TmSelect } from "@/components/tm/TmField";

const PREFILL_KEY = "alphacore.screener.prefill.v1";
const CONCENTRATION_THRESHOLD = 0.5; // ≥50% of top N in one sector → warn

interface FactorSelection {
  readonly id: string;
  readonly direction: ZooDirection;
  readonly weight: number;
}

/* ── Cap quintile bins (for RECS.CAPMIX) ─────────────────────────── */
const CAP_BUCKETS: readonly { lo: number; hi: number; label: string }[] = [
  { lo: 0, hi: 2e9, label: "<2B" },
  { lo: 2e9, hi: 10e9, label: "2-10B" },
  { lo: 10e9, hi: 50e9, label: "10-50B" },
  { lo: 50e9, hi: 200e9, label: "50-200B" },
  { lo: 200e9, hi: Infinity, label: "≥200B" },
];

export default function ScreenerPage() {
  const { locale } = useLocale();
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  const [selections, setSelections] = useState<readonly FactorSelection[]>([]);
  // Sectors: chip multi-select. Set<string> for O(1) toggle + dedup.
  const [availableSectors, setAvailableSectors] = useState<readonly string[]>([]);
  const [selectedSectors, setSelectedSectors] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [excludeInput, setExcludeInput] = useState("");
  const [minCap, setMinCap] = useState("");
  const [maxCap, setMaxCap] = useState("");
  const [lookback, setLookback] = useState(60);
  const [topN, setTopN] = useState(20);
  const [combineMethod, setCombineMethod] = useState<CombineMethod>("equal_z");
  const [asOfDate, setAsOfDate] = useState("");
  const [neutralize, setNeutralize] = useState<"none" | "sector">("none");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenerResponse | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [universeSize, setUniverseSize] = useState<number | null>(null);

  // Initial Zoo load + sectors fetch + universe count + handoff prefill.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const entries = listZoo();
    setZoo(entries);

    let preselectIds: string[] = [];
    try {
      const raw = window.sessionStorage.getItem(PREFILL_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { ids?: string[] };
        preselectIds = Array.isArray(parsed.ids) ? parsed.ids : [];
        window.sessionStorage.removeItem(PREFILL_KEY);
      }
    } catch {
      /* malformed prefill — ignore */
    }

    const validPreselect = preselectIds
      .filter((id) => entries.some((e) => e.id === id))
      .map<FactorSelection>((id) => {
        const e = entries.find((x) => x.id === id)!;
        return { id, direction: readDirection(e), weight: 1.0 };
      });
    setSelections(validPreselect);

    // Fetch sectors + universe count in parallel; both feed UI signage
    // (sector chip strip + N_UNIVERSE KPI). Failures are non-fatal.
    void (async () => {
      const [s, u] = await Promise.all([fetchSectors(), fetchUniverses()]);
      if (s.data) setAvailableSectors(s.data.sectors);
      if (u.data && u.data.universes.length > 0) {
        setUniverseSize(u.data.universes[0].ticker_count);
      }
    })();
  }, []);

  const selectedById = useMemo(() => {
    const m = new Map<string, FactorSelection>();
    for (const s of selections) m.set(s.id, s);
    return m;
  }, [selections]);

  function toggleFactor(entry: ZooEntry) {
    if (selectedById.has(entry.id)) {
      setSelections((prev) => prev.filter((s) => s.id !== entry.id));
    } else {
      setSelections((prev) => [
        ...prev,
        { id: entry.id, direction: readDirection(entry), weight: 1.0 },
      ]);
    }
  }

  function updateSelection(id: string, patch: Partial<FactorSelection>) {
    setSelections((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  }

  function toggleSector(sector: string) {
    setSelectedSectors((prev) => {
      const next = new Set(prev);
      if (next.has(sector)) next.delete(sector);
      else next.add(sector);
      return next;
    });
  }

  async function run() {
    if (selections.length === 0) {
      setError(t(locale, "screener.factors.empty"));
      return;
    }
    setRunning(true);
    setError(null);

    const factors: ScreenerFactorInput[] = selections.map((sel) => {
      const entry = zoo.find((e) => e.id === sel.id)!;
      return {
        spec: {
          name: entry.name,
          hypothesis: entry.hypothesis ?? "",
          expression: entry.expression,
          operators_used: [...extractOps(entry.expression)],
          lookback: 12,
          universe: "SP500",
          justification:
            entry.intuition ?? entry.hypothesis ?? "screener factor",
        },
        direction: sel.direction,
        weight: sel.weight,
      };
    });

    const exclude = excludeInput
      .split(/[,，\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    const sectors = Array.from(selectedSectors);

    const res = await runScreener({
      factors,
      universe_filter: {
        sectors: sectors.length > 0 ? sectors : undefined,
        min_cap: minCap.trim() ? Number(minCap) : undefined,
        max_cap: maxCap.trim() ? Number(maxCap) : undefined,
        exclude_tickers: exclude.length > 0 ? exclude : undefined,
      },
      lookback_days: lookback,
      top_n: topN,
      combine_method: combineMethod,
      as_of_date: asOfDate.trim() || null,
      neutralize,
    });

    if (res.error || !res.data) {
      setError(res.error ?? "unknown error");
    } else {
      setResult(res.data);
    }
    setRunning(false);
  }

  function exportCsv() {
    if (!result) return;
    const headers = [
      "rank",
      "ticker",
      "sector",
      "cap",
      "composite",
      ...result.factor_diagnostics.map((_, i) => `factor${i}_z`),
    ];
    const rows = result.recommendations.map((r) => [
      String(r.rank),
      r.ticker,
      r.sector ?? "",
      r.cap != null ? r.cap.toFixed(0) : "",
      r.composite_score.toFixed(4),
      ...r.per_factor_scores.map((p) => p.z.toFixed(4)),
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((c) => `"${c.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `screener_${result.metadata.as_of_date}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /* ── Aggregate stats from result (memoized) ────────────────────── */
  const aggregates = useMemo(() => {
    if (!result) return null;
    return computeAggregates(result);
  }, [result]);

  const survivorshipCorrected = result?.metadata.survivorship_corrected ?? false;
  const survivorshipAsOf = result?.metadata.membership_as_of ?? null;
  const concentrationWarn =
    aggregates !== null && aggregates.maxSectorShare >= CONCENTRATION_THRESHOLD;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">SCREENER</span>
        <TmSubbarSep />
        <TmSubbarKV label="ZOO" value={zoo.length.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="SELECTED" value={selections.length.toString()} />
        <TmSubbarSep />
        <TmSubbarKV label="TOP_N" value={topN.toString()} />
        {result && (
          <>
            <TmSubbarSep />
            <TmSubbarKV label="AS_OF" value={result.metadata.as_of_date} />
            <TmSubbarSep />
            <TmSubbarKV
              label="ELIGIBLE"
              value={result.metadata.n_eligible_tickers.toString()}
            />
          </>
        )}
        <TmSubbarSpacer />
        {concentrationWarn && aggregates && (
          <TmStatusPill tone="warn">
            {`SECTOR CONCENTRATION · ${aggregates.maxSectorLabel} ${(aggregates.maxSectorShare * 100).toFixed(0)}%`}
          </TmStatusPill>
        )}
        {result && (
          <TmStatusPill tone={survivorshipCorrected ? "ok" : "warn"}>
            {survivorshipCorrected
              ? `SP500-AS-OF · ${survivorshipAsOf ?? "—"}`
              : "LEGACY"}
          </TmStatusPill>
        )}
        {result?.metadata.neutralize === "sector" && (
          <TmStatusPill tone="ok">SECTOR-NEUTRAL</TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        {error && <TmStatusPill tone="err">ERROR</TmStatusPill>}
        <TmButton
          variant="primary"
          onClick={run}
          disabled={running || selections.length === 0}
          className="-my-1 px-3"
        >
          {running ? t(locale, "screener.running") : t(locale, "screener.run")}
        </TmButton>
      </TmSubbar>

      {error && (
        <TmPane title="ERROR" meta="screener run failed">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      <FactorPickerPane
        zoo={zoo}
        selectedById={selectedById}
        onToggle={toggleFactor}
        onUpdate={updateSelection}
        showWeights={combineMethod === "user_weighted"}
      />

      <TmCols2>
        <UniverseFilterPane
          availableSectors={availableSectors}
          selectedSectors={selectedSectors}
          onToggleSector={toggleSector}
          onClearSectors={() => setSelectedSectors(new Set())}
          excludeInput={excludeInput}
          onExclude={setExcludeInput}
          minCap={minCap}
          onMinCap={setMinCap}
          maxCap={maxCap}
          onMaxCap={setMaxCap}
        />
        <CombineParamsPane
          lookback={lookback}
          onLookback={setLookback}
          topN={topN}
          onTopN={setTopN}
          combineMethod={combineMethod}
          onCombineMethod={setCombineMethod}
          asOfDate={asOfDate}
          onAsOfDate={setAsOfDate}
          neutralize={neutralize}
          onNeutralize={setNeutralize}
        />
      </TmCols2>

      {result && aggregates && (
        <ResultsPane
          result={result}
          universeSize={universeSize}
          expandedTicker={expandedTicker}
          onExpand={setExpandedTicker}
          onExport={exportCsv}
        />
      )}

      {result && aggregates && (
        <TmCols2>
          <RecsSectorsPane
            breakdown={aggregates.sectorBreakdown}
            totalRecs={result.recommendations.length}
            warn={concentrationWarn}
          />
          <RecsCapMixPane
            breakdown={aggregates.capBreakdown}
            totalRecs={result.recommendations.length}
            unknownCount={aggregates.unknownCapCount}
          />
        </TmCols2>
      )}

      {result && aggregates && aggregates.factorContribution.length > 0 && (
        <AggregateContributionPane
          rows={aggregates.factorContribution}
          diagnostics={result.factor_diagnostics}
        />
      )}

      {result && result.factor_diagnostics.length > 0 && (
        <DiagnosticsPane
          diagnostics={result.factor_diagnostics}
          universeSize={universeSize}
        />
      )}

      {!result && !running && (
        <TmPane title="USAGE" meta="hint">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {t(locale, "screener.subtitle")}
          </p>
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── Aggregate computation ────────────────────────────────────────── */

interface AggregateBucket {
  readonly label: string;
  readonly count: number;
  readonly share: number; // 0..1
}
interface FactorContributionRow {
  readonly factor_idx: number;
  readonly absSum: number;
  readonly netSum: number;
  readonly share: number; // share of total absolute contribution
}
interface ScreenerAggregates {
  readonly sectorBreakdown: readonly AggregateBucket[];
  readonly capBreakdown: readonly AggregateBucket[];
  readonly unknownCapCount: number;
  readonly factorContribution: readonly FactorContributionRow[];
  readonly maxSectorShare: number;
  readonly maxSectorLabel: string;
}
function computeAggregates(result: ScreenerResponse): ScreenerAggregates {
  const recs = result.recommendations;
  const total = recs.length || 1;

  // Sector breakdown
  const sectorMap = new Map<string, number>();
  for (const r of recs) {
    const key = r.sector ?? "Unknown";
    sectorMap.set(key, (sectorMap.get(key) ?? 0) + 1);
  }
  const sectorBreakdown: AggregateBucket[] = Array.from(sectorMap.entries())
    .map(([label, count]) => ({ label, count, share: count / total }))
    .sort((a, b) => b.count - a.count);

  // Cap quintile bucketing
  const capCounts = CAP_BUCKETS.map(() => 0);
  let unknownCap = 0;
  for (const r of recs) {
    if (r.cap == null) {
      unknownCap += 1;
      continue;
    }
    const idx = CAP_BUCKETS.findIndex((b) => r.cap! > b.lo && r.cap! <= b.hi);
    if (idx >= 0) capCounts[idx] += 1;
    else unknownCap += 1;
  }
  const capBreakdown: AggregateBucket[] = CAP_BUCKETS.map((b, i) => ({
    label: b.label,
    count: capCounts[i],
    share: capCounts[i] / total,
  }));

  // Factor contribution: for each factor, sum |contribution| and signed
  // contribution across all top-N picks.
  const factorMap = new Map<number, { abs: number; net: number }>();
  for (const r of recs) {
    for (const p of r.per_factor_scores) {
      const cur = factorMap.get(p.factor_idx) ?? { abs: 0, net: 0 };
      cur.abs += Math.abs(p.contribution);
      cur.net += p.contribution;
      factorMap.set(p.factor_idx, cur);
    }
  }
  const totalAbs =
    Array.from(factorMap.values()).reduce((a, c) => a + c.abs, 0) || 1;
  const factorContribution: FactorContributionRow[] = Array.from(
    factorMap.entries(),
  )
    .map(([factor_idx, v]) => ({
      factor_idx,
      absSum: v.abs,
      netSum: v.net,
      share: v.abs / totalAbs,
    }))
    .sort((a, b) => b.absSum - a.absSum);

  const maxSector = sectorBreakdown[0] ?? { label: "—", share: 0 };

  return {
    sectorBreakdown,
    capBreakdown,
    unknownCapCount: unknownCap,
    factorContribution,
    maxSectorShare: maxSector.share,
    maxSectorLabel: maxSector.label,
  };
}

/* ── SCREENER.FACTORS pane ────────────────────────────────────────── */

function FactorPickerPane({
  zoo,
  selectedById,
  onToggle,
  onUpdate,
  showWeights,
}: {
  readonly zoo: readonly ZooEntry[];
  readonly selectedById: Map<string, FactorSelection>;
  readonly onToggle: (e: ZooEntry) => void;
  readonly onUpdate: (id: string, patch: Partial<FactorSelection>) => void;
  readonly showWeights: boolean;
}) {
  const { locale } = useLocale();
  const selectedCount = selectedById.size;

  if (zoo.length === 0) {
    return (
      <TmPane title="SCREENER.FACTORS" meta="ZOO EMPTY">
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "screener.factors.empty")}
        </p>
      </TmPane>
    );
  }

  return (
    <TmPane
      title="SCREENER.FACTORS"
      meta={`${selectedCount} / ${zoo.length} SELECTED`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "screener.factors.subtitle")}
      </p>
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[860px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns: showWeights
              ? "32px minmax(140px, 200px) 1fr minmax(140px, 160px) minmax(80px, 100px)"
              : "32px minmax(140px, 200px) 1fr minmax(140px, 160px)",
          }}
        >
          <PHeader>·</PHeader>
          <PHeader>{t(locale, "screener.factors.colName")}</PHeader>
          <PHeader>{t(locale, "zoo.colExpr")}</PHeader>
          <PHeader>{t(locale, "screener.factors.colDirection")}</PHeader>
          {showWeights && (
            <PHeader align="right">
              {t(locale, "screener.factors.colWeight")}
            </PHeader>
          )}
          {zoo.map((e) => {
            const sel = selectedById.get(e.id);
            return (
              <PickerRow
                key={e.id}
                entry={e}
                selection={sel}
                showWeights={showWeights}
                onToggle={() => onToggle(e)}
                onUpdate={(patch) => onUpdate(e.id, patch)}
              />
            );
          })}
        </div>
      </div>
    </TmPane>
  );
}

function PickerRow({
  entry,
  selection,
  showWeights,
  onToggle,
  onUpdate,
}: {
  readonly entry: ZooEntry;
  readonly selection: FactorSelection | undefined;
  readonly showWeights: boolean;
  readonly onToggle: () => void;
  readonly onUpdate: (patch: Partial<FactorSelection>) => void;
}) {
  const isSelected = Boolean(selection);
  const directionOptions = useMemo(
    () => [
      { value: "long_short", label: "long_short" },
      { value: "long_only", label: "long_only" },
      { value: "short_only", label: "short_only" },
    ],
    [],
  );
  return (
    <>
      <PCell>
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          className="cursor-pointer accent-[var(--tm-accent)]"
        />
      </PCell>
      <PCell>
        <span
          className={`truncate ${isSelected ? "text-tm-accent" : "text-tm-fg"}`}
        >
          {entry.name}
        </span>
      </PCell>
      <PCell title={entry.expression}>
        <span className="block truncate text-tm-fg-2">{entry.expression}</span>
      </PCell>
      <PCell>
        {selection ? (
          <TmSelect
            value={selection.direction}
            onChange={(v) => onUpdate({ direction: v as ZooDirection })}
            options={directionOptions}
            className="w-full"
          />
        ) : (
          <span className="text-tm-muted">—</span>
        )}
      </PCell>
      {showWeights && (
        <PCell align="right">
          {selection ? (
            <input
              type="number"
              min={0}
              max={10}
              step={0.1}
              value={selection.weight}
              onChange={(ev: ChangeEvent<HTMLInputElement>) =>
                onUpdate({ weight: Number(ev.target.value) })
              }
              className="h-7 w-full border border-tm-rule bg-tm-bg-2 px-2 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg outline-none focus:border-tm-accent"
            />
          ) : (
            <span className="text-tm-muted">—</span>
          )}
        </PCell>
      )}
    </>
  );
}

function PHeader({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function PCell({
  children,
  align = "left",
  title,
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
  readonly title?: string;
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
      title={title}
    >
      {children}
    </div>
  );
}

/* ── UNIVERSE.FILTER pane (with chip multi-select + presets) ─────── */

function UniverseFilterPane({
  availableSectors,
  selectedSectors,
  onToggleSector,
  onClearSectors,
  excludeInput,
  onExclude,
  minCap,
  onMinCap,
  maxCap,
  onMaxCap,
}: {
  readonly availableSectors: readonly string[];
  readonly selectedSectors: ReadonlySet<string>;
  readonly onToggleSector: (s: string) => void;
  readonly onClearSectors: () => void;
  readonly excludeInput: string;
  readonly onExclude: (v: string) => void;
  readonly minCap: string;
  readonly onMinCap: (v: string) => void;
  readonly maxCap: string;
  readonly onMaxCap: (v: string) => void;
}) {
  const { locale } = useLocale();
  const sectorMeta =
    availableSectors.length === 0
      ? "loading…"
      : `${selectedSectors.size} / ${availableSectors.length} GICS-1`;

  const capPresets: { label: string; value: string }[] = [
    { label: "10B", value: "10000000000" },
    { label: "100B", value: "100000000000" },
    { label: "1T", value: "1000000000000" },
  ];

  return (
    <TmPane title="UNIVERSE.FILTER" meta={sectorMeta}>
      <div className="flex flex-col gap-3 px-3 py-3">
        {/* Sectors chip multi-select */}
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "screener.universe.sectors")}
            </span>
            {selectedSectors.size > 0 && (
              <button
                type="button"
                onClick={onClearSectors}
                className="font-tm-mono text-[10px] text-tm-muted hover:text-tm-accent"
              >
                clear
              </button>
            )}
          </div>
          {availableSectors.length === 0 ? (
            <p className="font-tm-mono text-[10.5px] text-tm-muted">
              loading sectors…
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {availableSectors.map((s) => (
                <TmChip
                  key={s}
                  on={selectedSectors.has(s)}
                  onClick={() => onToggleSector(s)}
                >
                  {s}
                </TmChip>
              ))}
            </div>
          )}
          <p className="mt-1 font-tm-mono text-[10px] text-tm-muted">
            empty = include all sectors
          </p>
        </div>

        {/* Exclude tickers */}
        <TmInput
          label={t(locale, "screener.universe.exclude")}
          value={excludeInput}
          onChange={onExclude}
          placeholder="TSLA, NVDA"
          hint="upper-cased on submit"
        />

        {/* Cap inputs with preset chips */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <CapInputWithPresets
            label={t(locale, "screener.universe.minCap")}
            value={minCap}
            onChange={onMinCap}
            presets={capPresets}
            placeholder="10000000000"
          />
          <CapInputWithPresets
            label={t(locale, "screener.universe.maxCap")}
            value={maxCap}
            onChange={onMaxCap}
            presets={capPresets}
            placeholder="3000000000000"
          />
        </div>
      </div>
    </TmPane>
  );
}

function CapInputWithPresets({
  label,
  value,
  onChange,
  presets,
  placeholder,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly presets: readonly { label: string; value: string }[];
  readonly placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <TmInput
        label={label}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        type="number"
      />
      <div className="flex flex-wrap items-center gap-1">
        <span className="font-tm-mono text-[9.5px] uppercase tracking-[0.06em] text-tm-muted">
          preset
        </span>
        {presets.map((p) => (
          <TmChip
            key={p.value}
            on={value === p.value}
            onClick={() => onChange(value === p.value ? "" : p.value)}
          >
            {p.label}
          </TmChip>
        ))}
      </div>
    </div>
  );
}

/* ── COMBINE.PARAMS pane (with preset chips) ──────────────────────── */

function CombineParamsPane({
  lookback,
  onLookback,
  topN,
  onTopN,
  combineMethod,
  onCombineMethod,
  asOfDate,
  onAsOfDate,
  neutralize,
  onNeutralize,
}: {
  readonly lookback: number;
  readonly onLookback: (v: number) => void;
  readonly topN: number;
  readonly onTopN: (v: number) => void;
  readonly combineMethod: CombineMethod;
  readonly onCombineMethod: (v: CombineMethod) => void;
  readonly asOfDate: string;
  readonly onAsOfDate: (v: string) => void;
  readonly neutralize: "none" | "sector";
  readonly onNeutralize: (v: "none" | "sector") => void;
}) {
  const { locale } = useLocale();
  const methods: readonly { value: CombineMethod; labelKey: string }[] = [
    { value: "equal_z", labelKey: "screener.params.combineEqualZ" },
    { value: "ic_weighted", labelKey: "screener.params.combineIcWeighted" },
    { value: "user_weighted", labelKey: "screener.params.combineUserWeighted" },
  ];

  const lookbackPresets = [30, 60, 120, 252];
  const topNPresets = [10, 20, 50, 100];

  return (
    <TmPane title="COMBINE.PARAMS" meta="4 KNOBS">
      <div className="flex flex-col gap-3 px-3 py-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <SliderWithPresets
            label={t(locale, "screener.params.lookback")}
            min={10}
            max={252}
            step={10}
            value={lookback}
            unit="d"
            onChange={onLookback}
            presets={lookbackPresets}
          />
          <SliderWithPresets
            label={t(locale, "screener.params.topN")}
            min={5}
            max={100}
            step={5}
            value={topN}
            onChange={onTopN}
            presets={topNPresets}
          />
        </div>
        <div>
          <span className="mb-1 block font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "screener.params.combine")}
          </span>
          <div className="flex flex-wrap gap-1.5">
            {methods.map((m) => (
              <TmChip
                key={m.value}
                on={combineMethod === m.value}
                onClick={() => onCombineMethod(m.value)}
              >
                {t(locale, m.labelKey as Parameters<typeof t>[1])}
              </TmChip>
            ))}
          </div>
        </div>
        <div>
          <span className="mb-1 block font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "backtest.form.neutralize")}
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            {(["none", "sector"] as const).map((m) => (
              <TmChip
                key={m}
                on={neutralize === m}
                onClick={() => onNeutralize(m)}
              >
                {t(locale, `backtest.form.neutralize.${m}`)}
              </TmChip>
            ))}
            <span className="ml-2 font-tm-mono text-[10px] text-tm-muted">
              {t(locale, "backtest.form.neutralizeHint")}
            </span>
          </div>
        </div>
        <AsOfWithPresets value={asOfDate} onChange={onAsOfDate} label={t(locale, "screener.params.asOf")} />
      </div>
    </TmPane>
  );
}

function SliderWithPresets({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
  presets,
}: {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly unit?: string;
  readonly onChange: (n: number) => void;
  readonly presets: readonly number[];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between font-tm-mono">
        <label className="text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
          {label}
        </label>
        <span className="text-[12px] tabular-nums text-tm-fg">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e: ChangeEvent<HTMLInputElement>) =>
          onChange(Number(e.target.value))
        }
        className="h-1 w-full accent-[var(--tm-accent)]"
      />
      <div className="flex flex-wrap items-center gap-1">
        <span className="font-tm-mono text-[9.5px] uppercase tracking-[0.06em] text-tm-muted">
          preset
        </span>
        {presets.map((p) => (
          <TmChip key={p} on={value === p} onClick={() => onChange(p)}>
            {p}
            {unit}
          </TmChip>
        ))}
      </div>
    </div>
  );
}

function AsOfWithPresets({
  value,
  onChange,
  label,
}: {
  readonly value: string;
  readonly onChange: (v: string) => void;
  readonly label: string;
}) {
  // Compute preset dates relative to today. "today" sends empty (panel
  // last day) so we don't ship a date the panel might not cover.
  function offsetDate(daysBack: number): string {
    const d = new Date();
    d.setDate(d.getDate() - daysBack);
    return d.toISOString().slice(0, 10);
  }
  const presets: { label: string; value: string }[] = [
    { label: "today", value: "" },
    { label: "-7d", value: offsetDate(7) },
    { label: "-30d", value: offsetDate(30) },
    { label: "-90d", value: offsetDate(90) },
  ];
  return (
    <div className="flex flex-col gap-1.5">
      <TmInput
        label={label}
        value={value}
        onChange={onChange}
        placeholder="YYYY-MM-DD"
        hint="leave blank for panel last day"
      />
      <div className="flex flex-wrap items-center gap-1">
        <span className="font-tm-mono text-[9.5px] uppercase tracking-[0.06em] text-tm-muted">
          preset
        </span>
        {presets.map((p) => (
          <TmChip key={p.label} on={value === p.value} onClick={() => onChange(p.value)}>
            {p.label}
          </TmChip>
        ))}
      </div>
    </div>
  );
}

/* ── RESULTS pane ─────────────────────────────────────────────────── */

function ResultsPane({
  result,
  universeSize,
  expandedTicker,
  onExpand,
  onExport,
}: {
  readonly result: ScreenerResponse;
  readonly universeSize: number | null;
  readonly expandedTicker: string | null;
  readonly onExpand: (t: string | null) => void;
  readonly onExport: () => void;
}) {
  const { locale } = useLocale();
  const recs = result.recommendations;
  const { isWatched } = useWatchlist();
  const subtitle = t(locale, "screener.results.subtitle").replace(
    "{n}",
    String(recs.length),
  );
  const composites = recs.map((r) => r.composite_score);
  const meanComposite =
    composites.length > 0
      ? composites.reduce((a, b) => a + b, 0) / composites.length
      : 0;
  const topScore = composites[0] ?? 0;
  const eligible = result.metadata.n_eligible_tickers;
  const eligRate =
    universeSize && universeSize > 0 ? (eligible / universeSize) * 100 : null;

  return (
    <TmPane
      title="SCREENER.RESULTS"
      meta={`${recs.length} TOP · ${result.metadata.method}`}
    >
      <TmKpiGrid>
        <TmKpi
          label="N_UNIVERSE"
          value={universeSize != null ? universeSize.toString() : "—"}
          sub="full SP500 panel"
        />
        <TmKpi
          label="N_ELIGIBLE"
          value={eligible.toString()}
          sub="post-filter universe"
        />
        <TmKpi
          label="ELIG_RATE"
          value={eligRate != null ? `${eligRate.toFixed(1)}%` : "—"}
          tone={
            eligRate == null ? "default" : eligRate > 50 ? "pos" : "warn"
          }
          sub="elig / universe"
        />
        <TmKpi
          label="TOP_SCORE"
          value={topScore.toFixed(3)}
          tone={topScore > 0 ? "pos" : "neg"}
          sub="rank #1"
        />
        <TmKpi
          label="AVG_SCORE"
          value={meanComposite.toFixed(3)}
          tone={meanComposite > 0 ? "pos" : "neg"}
          sub={`${recs.length} basket`}
        />
        <TmKpi
          label="METHOD"
          value={result.metadata.method.toUpperCase()}
          sub="combine"
        />
      </TmKpiGrid>

      <div className="flex items-center justify-between border-t border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          {subtitle}
        </span>
        <TmButton
          variant="ghost"
          onClick={onExport}
          className="-my-1 h-6 px-2 text-[10px]"
        >
          {t(locale, "screener.results.exportCsv")}
        </TmButton>
      </div>

      {recs.length === 0 ? (
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "screener.results.empty")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <div
            className="grid min-w-[800px] gap-px bg-tm-rule"
            style={{
              gridTemplateColumns:
                "48px minmax(80px, 100px) minmax(140px, 1fr) minmax(80px, 100px) minmax(80px, 100px) 32px",
            }}
          >
            <RHeader>{t(locale, "screener.results.colRank")}</RHeader>
            <RHeader>{t(locale, "screener.results.colTicker")}</RHeader>
            <RHeader>{t(locale, "screener.results.colSector")}</RHeader>
            <RHeader align="right">{t(locale, "screener.results.colCap")}</RHeader>
            <RHeader align="right">
              {t(locale, "screener.results.colComposite")}
            </RHeader>
            <RHeader>·</RHeader>
            {recs.map((r) => {
              const isOpen = expandedTicker === r.ticker;
              return (
                <Fragment key={r.ticker}>
                  <RCell>
                    <span className="text-tm-muted">
                      {String(r.rank).padStart(2, "0")}
                    </span>
                  </RCell>
                  <RCell>
                    <span className="font-semibold text-tm-accent">
                      {isWatched(r.ticker) ? (
                        <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" />
                      ) : null}
                      {r.ticker}
                    </span>
                  </RCell>
                  <RCell>
                    <span className="text-tm-fg-2">{r.sector ?? "—"}</span>
                  </RCell>
                  <RCell align="right">
                    <span className="tabular-nums text-tm-muted">
                      {r.cap != null ? formatCap(r.cap) : "—"}
                    </span>
                  </RCell>
                  <RCell align="right">
                    <span
                      className={`tabular-nums ${r.composite_score >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
                    >
                      {r.composite_score >= 0 ? "+" : ""}
                      {r.composite_score.toFixed(3)}
                    </span>
                  </RCell>
                  <RCell align="right">
                    <button
                      type="button"
                      onClick={() => onExpand(isOpen ? null : r.ticker)}
                      className="font-tm-mono text-tm-muted hover:text-tm-accent"
                    >
                      {isOpen ? "▾" : "▸"}
                    </button>
                  </RCell>
                  {isOpen && (
                    <div
                      className="bg-tm-bg-2 px-3 py-3"
                      style={{ gridColumn: "1 / -1" }}
                    >
                      <ContributionBars
                        scores={r.per_factor_scores}
                        diagnostics={result.factor_diagnostics}
                      />
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        </div>
      )}
    </TmPane>
  );
}

function RHeader({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted ${
        align === "right" ? "text-right" : ""
      }`}
    >
      {children}
    </div>
  );
}

function RCell({
  children,
  align = "left",
}: {
  readonly children: React.ReactNode;
  readonly align?: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center bg-tm-bg px-2 py-1 font-tm-mono text-[11px] ${
        align === "right" ? "justify-end" : ""
      }`}
    >
      {children}
    </div>
  );
}

function ContributionBars({
  scores,
  diagnostics,
}: {
  readonly scores: ScreenerResponse["recommendations"][number]["per_factor_scores"];
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
}) {
  const max = Math.max(0.1, ...scores.map((s) => Math.abs(s.contribution)));
  return (
    <div className="flex flex-col gap-1">
      {scores.map((s) => {
        const diag = diagnostics[s.factor_idx];
        const pct = (Math.abs(s.contribution) / max) * 100;
        const positive = s.contribution >= 0;
        return (
          <div
            key={s.factor_idx}
            className="flex items-center gap-3 font-tm-mono text-[11px]"
          >
            <code
              className="w-48 truncate text-tm-fg"
              title={diag?.expression ?? ""}
            >
              {diag?.expression ?? `factor[${s.factor_idx}]`}
            </code>
            <div className="relative flex h-3 flex-1 items-center bg-tm-bg-3">
              <div
                className="absolute left-1/2 h-full w-px bg-tm-rule-2"
                aria-hidden="true"
              />
              <div
                className={`absolute h-full ${positive ? "bg-tm-pos" : "bg-tm-neg"}`}
                style={{
                  [positive ? "left" : "right"]: "50%",
                  width: `${pct / 2}%`,
                }}
              />
            </div>
            <span
              className={`w-16 text-right tabular-nums ${positive ? "text-tm-pos" : "text-tm-neg"}`}
            >
              {s.contribution >= 0 ? "+" : ""}
              {s.contribution.toFixed(3)}
            </span>
            <span className="w-14 text-right tabular-nums text-tm-muted">
              z={s.z.toFixed(2)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ── RECS.SECTORS pane ────────────────────────────────────────────── */

function RecsSectorsPane({
  breakdown,
  totalRecs,
  warn,
}: {
  readonly breakdown: readonly AggregateBucket[];
  readonly totalRecs: number;
  readonly warn: boolean;
}) {
  return (
    <TmPane
      title="RECS.SECTORS"
      meta={`${breakdown.length} GROUPS · ${totalRecs} TOP-N`}
    >
      {breakdown.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
          no sector data.
        </p>
      ) : (
        <ul className="flex flex-col">
          {breakdown.map((b, i) => {
            const isMax = i === 0;
            const tone =
              warn && isMax
                ? "text-tm-warn"
                : isMax
                  ? "text-tm-accent"
                  : "text-tm-fg-2";
            const barClass =
              warn && isMax ? "bg-tm-warn" : "bg-tm-accent";
            return (
              <li
                key={b.label}
                className="grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0"
                style={{
                  gridTemplateColumns: "minmax(140px, 180px) 1fr 50px 50px",
                }}
              >
                <span className={`truncate font-tm-mono text-[11px] ${tone}`}>
                  {b.label}
                </span>
                <div className="relative h-3 w-full bg-tm-bg-2">
                  <div
                    className={`h-full opacity-60 ${barClass}`}
                    style={{ width: `${b.share * 100}%` }}
                  />
                </div>
                <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
                  {b.count}
                </span>
                <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-muted">
                  {(b.share * 100).toFixed(0)}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </TmPane>
  );
}

/* ── RECS.CAPMIX pane ─────────────────────────────────────────────── */

function RecsCapMixPane({
  breakdown,
  totalRecs,
  unknownCount,
}: {
  readonly breakdown: readonly AggregateBucket[];
  readonly totalRecs: number;
  readonly unknownCount: number;
}) {
  // When every recommendation lacks a cap value (panel.cap all-NaN), 5
  // empty bars look broken. Show a single empty-state instead so the
  // user knows it's a data gap, not a UI hang.
  const allUnknown = totalRecs > 0 && unknownCount === totalRecs;

  if (allUnknown) {
    return (
      <TmPane title="RECS.CAPMIX" meta="NO CAP DATA">
        <div className="flex flex-col gap-1.5 px-3 py-3 font-tm-mono text-[11px]">
          <p className="text-tm-warn">
            ▸ all {totalRecs} recommendations missing cap data.
          </p>
          <p className="leading-relaxed text-tm-muted">
            panel field <code className="text-tm-fg-2">cap</code> has 0%
            coverage on this universe — column exists but values are all-NaN.
            cap-based filters (MIN_CAP / MAX_CAP) will also silently filter
            to empty until backfilled. cap is computed as{" "}
            <code className="text-tm-fg-2">close × shares_outstanding</code>;
            either WRDS Compustat fundq <code>cshoq</code> or yfinance pull
            needs to repopulate.
          </p>
        </div>
      </TmPane>
    );
  }

  const unknownShare = totalRecs > 0 ? unknownCount / totalRecs : 0;
  const meta = unknownCount
    ? `5 BUCKETS · ${totalRecs} TOP-N · ${unknownCount} UNKNOWN`
    : `5 BUCKETS · ${totalRecs} TOP-N`;
  return (
    <TmPane title="RECS.CAPMIX" meta={meta}>
      <ul className="flex flex-col">
        {breakdown.map((b) => (
          <li
            key={b.label}
            className="grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0"
            style={{
              gridTemplateColumns: "minmax(80px, 100px) 1fr 50px 50px",
            }}
          >
            <span className="font-tm-mono text-[11px] text-tm-info">
              {b.label}
            </span>
            <div className="relative h-3 w-full bg-tm-bg-2">
              <div
                className="h-full bg-tm-info opacity-60"
                style={{ width: `${b.share * 100}%` }}
              />
            </div>
            <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
              {b.count}
            </span>
            <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-muted">
              {(b.share * 100).toFixed(0)}%
            </span>
          </li>
        ))}
        {unknownCount > 0 && (
          <li
            className="grid items-center gap-3 border-b border-tm-rule bg-tm-bg-2 px-3 py-1 last:border-b-0"
            style={{
              gridTemplateColumns: "minmax(80px, 100px) 1fr 50px 50px",
            }}
          >
            <span className="font-tm-mono text-[11px] text-tm-warn">
              UNKNOWN
            </span>
            <div className="relative h-3 w-full bg-tm-bg-3">
              <div
                className="h-full bg-tm-warn opacity-50"
                style={{ width: `${unknownShare * 100}%` }}
              />
            </div>
            <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
              {unknownCount}
            </span>
            <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-warn">
              {(unknownShare * 100).toFixed(0)}%
            </span>
          </li>
        )}
      </ul>
    </TmPane>
  );
}

/* ── AGGREGATE.CONTRIBUTION pane ──────────────────────────────────── */

function AggregateContributionPane({
  rows,
  diagnostics,
}: {
  readonly rows: readonly FactorContributionRow[];
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
}) {
  const maxAbs = rows[0]?.absSum ?? 1;
  return (
    <TmPane
      title="AGGREGATE.CONTRIBUTION"
      meta={`${rows.length} FACTORS · sum |contribution| across top-N`}
    >
      <ul className="flex flex-col">
        {rows.map((r) => {
          const diag = diagnostics[r.factor_idx];
          const widthPct = (r.absSum / maxAbs) * 100;
          const netPositive = r.netSum >= 0;
          return (
            <li
              key={r.factor_idx}
              className="grid items-center gap-3 border-b border-tm-rule px-3 py-1.5 last:border-b-0"
              style={{
                gridTemplateColumns:
                  "minmax(220px, 320px) 1fr minmax(80px, 100px) 50px",
              }}
            >
              <span
                className="truncate font-tm-mono text-[11px] text-tm-accent"
                title={diag?.expression ?? `factor[${r.factor_idx}]`}
              >
                {diag?.expression ?? `factor[${r.factor_idx}]`}
              </span>
              <div className="relative h-3 w-full bg-tm-bg-2">
                <div
                  className={`h-full opacity-70 ${netPositive ? "bg-tm-pos" : "bg-tm-neg"}`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span
                className={`text-right font-tm-mono text-[10.5px] tabular-nums ${netPositive ? "text-tm-pos" : "text-tm-neg"}`}
              >
                {netPositive ? "+" : ""}
                {r.netSum.toFixed(3)}
              </span>
              <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-muted">
                {(r.share * 100).toFixed(0)}%
              </span>
            </li>
          );
        })}
      </ul>
      <p className="border-t border-tm-rule px-3 py-1.5 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
        bar = sum |contribution|; share % of total | sign = net signed sum.
        a single factor with ≥60% share dominates the basket.
      </p>
    </TmPane>
  );
}

/* ── DIAGNOSTICS pane (with IC + n_eligible bars) ─────────────────── */

function DiagnosticsPane({
  diagnostics,
  universeSize,
}: {
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
  readonly universeSize: number | null;
}) {
  const { locale } = useLocale();
  // IC bar scale: max(|ic|) across diagnostics, floored at 0.05 so a
  // tiny-IC factor doesn't visually dominate by being normalized to full.
  const maxAbsIc = Math.max(
    0.05,
    ...diagnostics.map((d) => Math.abs(d.in_window_ic)),
  );
  const denom = universeSize && universeSize > 0 ? universeSize : null;
  return (
    <TmPane
      title="SCREENER.DIAGNOSTICS"
      meta={`${diagnostics.length} FACTORS`}
    >
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[840px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "1fr minmax(140px, 180px) minmax(80px, 100px) minmax(160px, 200px)",
          }}
        >
          <RHeader>{t(locale, "screener.diagnostics.colExpr")}</RHeader>
          <RHeader>{t(locale, "screener.diagnostics.colIc")}</RHeader>
          <RHeader align="right">
            {t(locale, "screener.diagnostics.colWeight")}
          </RHeader>
          <RHeader>{t(locale, "screener.diagnostics.colEligible")}</RHeader>
          {diagnostics.map((d) => {
            const ic = d.in_window_ic;
            const icPct = (Math.abs(ic) / maxAbsIc) * 100;
            const positive = ic >= 0;
            const eligPct = denom ? (d.n_eligible / denom) * 100 : null;
            return (
              <Fragment key={d.factor_idx}>
                <RCell>
                  <span
                    className="block truncate text-tm-fg-2"
                    title={d.expression}
                  >
                    {d.expression}
                  </span>
                </RCell>
                <div className="flex items-center gap-2 bg-tm-bg px-2 py-1 font-tm-mono">
                  <div className="relative flex h-3 flex-1 items-center bg-tm-bg-3">
                    <div
                      className="absolute left-1/2 h-full w-px bg-tm-rule-2"
                      aria-hidden="true"
                    />
                    <div
                      className={`absolute h-full ${positive ? "bg-tm-pos" : "bg-tm-neg"}`}
                      style={{
                        [positive ? "left" : "right"]: "50%",
                        width: `${icPct / 2}%`,
                      }}
                    />
                  </div>
                  <span
                    className={`w-12 text-right text-[10.5px] tabular-nums ${positive ? "text-tm-pos" : "text-tm-neg"}`}
                  >
                    {ic.toFixed(3)}
                  </span>
                </div>
                <RCell align="right">
                  <span className="tabular-nums text-tm-fg">
                    {(d.used_weight * 100).toFixed(1)}%
                  </span>
                </RCell>
                <div className="flex items-center gap-2 bg-tm-bg px-2 py-1 font-tm-mono">
                  <div className="relative flex h-3 flex-1 items-center bg-tm-bg-2">
                    {eligPct != null && (
                      <div
                        className="h-full bg-tm-info opacity-60"
                        style={{ width: `${eligPct}%` }}
                      />
                    )}
                  </div>
                  <span className="w-16 text-right text-[10.5px] tabular-nums text-tm-muted">
                    {d.n_eligible}
                    {eligPct != null
                      ? ` / ${eligPct.toFixed(0)}%`
                      : ""}
                  </span>
                </div>
              </Fragment>
            );
          })}
        </div>
      </div>
    </TmPane>
  );
}

/* ── Helpers ──────────────────────────────────────────────────────── */

function formatCap(cap: number): string {
  if (cap >= 1e12) return `${(cap / 1e12).toFixed(2)}T`;
  if (cap >= 1e9) return `${(cap / 1e9).toFixed(1)}B`;
  if (cap >= 1e6) return `${(cap / 1e6).toFixed(0)}M`;
  return cap.toFixed(0);
}
