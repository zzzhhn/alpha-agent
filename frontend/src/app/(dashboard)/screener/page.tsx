"use client";

/**
 * Screener page — workstation port (Stage 3 · 6/9).
 *
 * Layout: TmSubbar (factor counts + status + run button) →
 *   SCREENER.FACTORS pane (Zoo factor picker, sortable hairline grid) →
 *   TmCols2 (UNIVERSE.FILTER | COMBINE.PARAMS) →
 *   RESULTS pane (KPI strip + recommendations + expandable contribution
 *     bars + CSV export action) →
 *   DIAGNOSTICS pane (per-factor IC / weight / eligibility table).
 *
 * Behavior preserved byte-for-byte: sessionStorage prefill from /factors
 * (PREFILL_KEY → ids[]), runScreener payload assembly (sectors/exclude
 * tokenize the same way), CSV export with same header order, expand /
 * collapse one ticker at a time, survivorship + neutralize badges.
 */

import { Fragment, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import {
  listZoo,
  readDirection,
  type ZooEntry,
  type ZooDirection,
} from "@/lib/factor-zoo";
import { runScreener } from "@/lib/api";
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

interface FactorSelection {
  readonly id: string;
  readonly direction: ZooDirection;
  readonly weight: number;
}

export default function ScreenerPage() {
  const { locale } = useLocale();
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  const [selections, setSelections] = useState<readonly FactorSelection[]>([]);
  const [sectorsInput, setSectorsInput] = useState("");
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

  // Initial Zoo load + handoff prefill from /factors.
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

    const sectors = sectorsInput
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const exclude = excludeInput
      .split(/[,，\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

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

  const survivorshipCorrected = result?.metadata.survivorship_corrected ?? false;
  const survivorshipAsOf = result?.metadata.membership_as_of ?? null;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">SCREENER</span>
        <TmSubbarSep />
        <TmSubbarKV label="ZOO" value={zoo.length.toString()} />
        <TmSubbarSep />
        <TmSubbarKV
          label="SELECTED"
          value={selections.length.toString()}
        />
        <TmSubbarSep />
        <TmSubbarKV label="TOP_N" value={topN.toString()} />
        {result && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="AS_OF"
              value={result.metadata.as_of_date}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label="ELIGIBLE"
              value={result.metadata.n_eligible_tickers.toString()}
            />
          </>
        )}
        <TmSubbarSpacer />
        {result && (
          <TmStatusPill tone={survivorshipCorrected ? "ok" : "warn"}>
            {survivorshipCorrected
              ? `SP500-AS-OF · ${survivorshipAsOf ?? "—"}`
              : "LEGACY (NO MEMBERSHIP MASK)"}
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

      {/* SCREENER.FACTORS — Zoo picker */}
      <FactorPickerPane
        zoo={zoo}
        selectedById={selectedById}
        onToggle={toggleFactor}
        onUpdate={updateSelection}
        showWeights={combineMethod === "user_weighted"}
      />

      {/* UNIVERSE.FILTER | COMBINE.PARAMS */}
      <TmCols2>
        <UniverseFilterPane
          sectorsInput={sectorsInput}
          onSectors={setSectorsInput}
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

      {result && (
        <ResultsPane
          result={result}
          expandedTicker={expandedTicker}
          onExpand={setExpandedTicker}
          onExport={exportCsv}
        />
      )}

      {result && result.factor_diagnostics.length > 0 && (
        <DiagnosticsPane diagnostics={result.factor_diagnostics} />
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

/* ── UNIVERSE.FILTER pane ─────────────────────────────────────────── */

function UniverseFilterPane({
  sectorsInput,
  onSectors,
  excludeInput,
  onExclude,
  minCap,
  onMinCap,
  maxCap,
  onMaxCap,
}: {
  readonly sectorsInput: string;
  readonly onSectors: (v: string) => void;
  readonly excludeInput: string;
  readonly onExclude: (v: string) => void;
  readonly minCap: string;
  readonly onMinCap: (v: string) => void;
  readonly maxCap: string;
  readonly onMaxCap: (v: string) => void;
}) {
  const { locale } = useLocale();
  return (
    <TmPane title="UNIVERSE.FILTER" meta="4 FIELDS">
      <div className="grid grid-cols-1 gap-3 px-3 py-3 md:grid-cols-2">
        <TmInput
          label={t(locale, "screener.universe.sectors")}
          value={sectorsInput}
          onChange={onSectors}
          placeholder="Technology, Healthcare"
          hint="comma / space separated; case-insensitive"
        />
        <TmInput
          label={t(locale, "screener.universe.exclude")}
          value={excludeInput}
          onChange={onExclude}
          placeholder="TSLA, NVDA"
          hint="upper-cased on submit"
        />
        <TmInput
          label={t(locale, "screener.universe.minCap")}
          value={minCap}
          onChange={onMinCap}
          placeholder="10000000000"
          type="number"
        />
        <TmInput
          label={t(locale, "screener.universe.maxCap")}
          value={maxCap}
          onChange={onMaxCap}
          placeholder="3000000000000"
          type="number"
        />
      </div>
    </TmPane>
  );
}

/* ── COMBINE.PARAMS pane ──────────────────────────────────────────── */

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
  return (
    <TmPane title="COMBINE.PARAMS" meta="4 KNOBS">
      <div className="flex flex-col gap-3 px-3 py-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <TmSlider
            label={t(locale, "screener.params.lookback")}
            min={10}
            max={252}
            step={10}
            value={lookback}
            unit="d"
            onChange={onLookback}
          />
          <TmSlider
            label={t(locale, "screener.params.topN")}
            min={5}
            max={100}
            step={5}
            value={topN}
            onChange={onTopN}
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
        <TmInput
          label={t(locale, "screener.params.asOf")}
          value={asOfDate}
          onChange={onAsOfDate}
          placeholder="YYYY-MM-DD"
          hint="leave blank for panel last day"
        />
      </div>
    </TmPane>
  );
}

/* ── Slider ───────────────────────────────────────────────────────── */

function TmSlider({
  label,
  value,
  min,
  max,
  step = 1,
  unit = "",
  onChange,
}: {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly unit?: string;
  readonly onChange: (n: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
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
    </div>
  );
}

/* ── RESULTS pane ─────────────────────────────────────────────────── */

function ResultsPane({
  result,
  expandedTicker,
  onExpand,
  onExport,
}: {
  readonly result: ScreenerResponse;
  readonly expandedTicker: string | null;
  readonly onExpand: (t: string | null) => void;
  readonly onExport: () => void;
}) {
  const { locale } = useLocale();
  const recs = result.recommendations;
  const subtitle = t(locale, "screener.results.subtitle").replace(
    "{n}",
    String(recs.length),
  );

  // Surface aggregate stats above the table — gives a 1-glance read on
  // composite quality vs the eligible universe.
  const composites = recs.map((r) => r.composite_score);
  const meanComposite =
    composites.length > 0
      ? composites.reduce((a, b) => a + b, 0) / composites.length
      : 0;
  const topScore = composites[0] ?? 0;

  return (
    <TmPane
      title="SCREENER.RESULTS"
      meta={`${recs.length} TOP · ${result.metadata.method}`}
    >
      <TmKpiGrid>
        <TmKpi
          label="N_ELIGIBLE"
          value={result.metadata.n_eligible_tickers.toString()}
          sub="post-filter universe"
        />
        <TmKpi
          label="TOP_SCORE"
          value={topScore.toFixed(3)}
          tone={topScore > 0 ? "pos" : "neg"}
          sub="rank #1 composite"
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

/* ── DIAGNOSTICS pane ─────────────────────────────────────────────── */

function DiagnosticsPane({
  diagnostics,
}: {
  readonly diagnostics: ScreenerResponse["factor_diagnostics"];
}) {
  const { locale } = useLocale();
  return (
    <TmPane
      title="SCREENER.DIAGNOSTICS"
      meta={`${diagnostics.length} FACTORS`}
    >
      <div className="overflow-x-auto">
        <div
          className="grid min-w-[700px] gap-px bg-tm-rule"
          style={{
            gridTemplateColumns: "1fr minmax(80px, 100px) minmax(80px, 100px) minmax(100px, 120px)",
          }}
        >
          <RHeader>{t(locale, "screener.diagnostics.colExpr")}</RHeader>
          <RHeader align="right">
            {t(locale, "screener.diagnostics.colIc")}
          </RHeader>
          <RHeader align="right">
            {t(locale, "screener.diagnostics.colWeight")}
          </RHeader>
          <RHeader align="right">
            {t(locale, "screener.diagnostics.colEligible")}
          </RHeader>
          {diagnostics.map((d) => (
            <Fragment key={d.factor_idx}>
              <RCell>
                <span
                  className="block truncate text-tm-fg-2"
                  title={d.expression}
                >
                  {d.expression}
                </span>
              </RCell>
              <RCell align="right">
                <span
                  className={`tabular-nums ${d.in_window_ic > 0 ? "text-tm-pos" : d.in_window_ic < 0 ? "text-tm-neg" : "text-tm-fg"}`}
                >
                  {d.in_window_ic.toFixed(3)}
                </span>
              </RCell>
              <RCell align="right">
                <span className="tabular-nums text-tm-fg">
                  {(d.used_weight * 100).toFixed(1)}%
                </span>
              </RCell>
              <RCell align="right">
                <span className="tabular-nums text-tm-muted">
                  {d.n_eligible}
                </span>
              </RCell>
            </Fragment>
          ))}
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
