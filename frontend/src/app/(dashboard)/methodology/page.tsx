"use client";

/**
 * Methodology page — workstation port v2 (Stage 3 · 3/9, density rework).
 *
 * v1 left ~600px of bottom whitespace per tab — the page only carried
 * 12 tokens of info on a workstation canvas built for 200+. v2 fills
 * the canvas without scaling fonts:
 *
 *   - Data tab: 8-cell KPI strip + 2-col (Pipeline | Sectors+BiasGuards)
 *     + full PANEL.SCHEMA listing every field's type / source / group.
 *   - Operators tab: 4-cell summary + single chip-filtered catalog
 *     (replaces N stacked category panes with one dense scrollable list).
 *   - Backtest tab: 4-cell summary + categorized formulas with chip
 *     filter + 4 portfolio rules.
 *
 * Schema constants are colocated below; they document the live `_Panel`
 * dataclass at alpha_agent/factor_engine/factor_backtest.py:143.
 * Fundamental field list mirrors `_V2_FUNDAMENTAL_FIELDS` (line 98).
 *
 * Per-fetch error tracking + targeted retry preserved from v1.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmScreen, TmPane, TmCols2 } from "@/components/tm/TmPane";
import {
  TmSubbar,
  TmSubbarKV,
  TmSubbarSep,
  TmSubbarSpacer,
  TmChip,
  TmStatusPill,
} from "@/components/tm/TmSubbar";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmButton } from "@/components/tm/TmButton";
import {
  fetchOperandCatalogWithSignatures,
  fetchSectors,
  fetchUniverses,
  fetchCoverage,
  invalidateDataCache,
} from "@/lib/api";
import type {
  OperandCatalogResponse,
  UniverseListResponse,
  CoverageResponse,
} from "@/lib/types";

type Tab = "data" | "operators" | "backtest";

interface OperatorWithSignature {
  readonly name: string;
  readonly category?: string;
  readonly tier?: string;
  readonly implemented?: boolean;
  readonly signature?: string;
  readonly source_snippet?: string;
}

/* ── Static panel schema (matches _Panel dataclass) ───────────────── */

interface SchemaField {
  readonly group: "PRICES" | "META" | "FUNDAMENTALS" | "INSIDER" | "MASKS" | "BENCHMARKS";
  readonly name: string;
  readonly type: string;
  readonly source: string;
  readonly coverage: "full" | "sparse" | "quarterly" | "snapshot";
}

const PANEL_SCHEMA: readonly SchemaField[] = [
  // PRICES / VOLUME
  { group: "PRICES", name: "close", type: "float64 (T,N)", source: "Alpaca daily / yfinance", coverage: "full" },
  { group: "PRICES", name: "open", type: "float64 (T,N)", source: "Alpaca daily / yfinance", coverage: "full" },
  { group: "PRICES", name: "high", type: "float64 (T,N)", source: "Alpaca daily / yfinance", coverage: "full" },
  { group: "PRICES", name: "low", type: "float64 (T,N)", source: "Alpaca daily / yfinance", coverage: "full" },
  { group: "PRICES", name: "volume", type: "float64 (T,N)", source: "Alpaca daily / yfinance", coverage: "full" },
  // META (broadcast snapshots — same per-row vector across T)
  { group: "META", name: "cap", type: "float64 (T,N)", source: "close × shares_outstanding", coverage: "full" },
  { group: "META", name: "sector", type: "str (T,N)", source: "yfinance .info (broadcast)", coverage: "snapshot" },
  { group: "META", name: "industry", type: "str (T,N)", source: "yfinance .info (broadcast)", coverage: "snapshot" },
  { group: "META", name: "exchange", type: "str (T,N)", source: "yfinance .info (broadcast)", coverage: "snapshot" },
  { group: "META", name: "currency", type: "str (T,N)", source: "yfinance .info (broadcast)", coverage: "snapshot" },
  // FUNDAMENTALS — PIT-joined from WRDS Compustat fundq, RDQ ≤ t
  { group: "FUNDAMENTALS", name: "revenue", type: "float64 (T,N)", source: "WRDS fundq · revtq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "net_income_adjusted", type: "float64 (T,N)", source: "WRDS fundq · niq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "ebitda", type: "float64 (T,N)", source: "WRDS fundq · oibdpq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "eps", type: "float64 (T,N)", source: "WRDS fundq · epspxq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "equity", type: "float64 (T,N)", source: "WRDS fundq · seqq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "assets", type: "float64 (T,N)", source: "WRDS fundq · atq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "free_cash_flow", type: "float64 (T,N)", source: "WRDS fundq · oancfy − capxy", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "gross_profit", type: "float64 (T,N)", source: "WRDS fundq · gpq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "operating_income", type: "float64 (T,N)", source: "WRDS fundq · oiadpq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "cost_of_goods_sold", type: "float64 (T,N)", source: "WRDS fundq · cogsq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "ebit", type: "float64 (T,N)", source: "WRDS fundq · oiadpq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "current_assets", type: "float64 (T,N)", source: "WRDS fundq · actq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "current_liabilities", type: "float64 (T,N)", source: "WRDS fundq · lctq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "long_term_debt", type: "float64 (T,N)", source: "WRDS fundq · dlttq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "short_term_debt", type: "float64 (T,N)", source: "WRDS fundq · dlcq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "cash_and_equivalents", type: "float64 (T,N)", source: "WRDS fundq · cheq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "retained_earnings", type: "float64 (T,N)", source: "WRDS fundq · req", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "goodwill", type: "float64 (T,N)", source: "WRDS fundq · gdwlq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "operating_cash_flow", type: "float64 (T,N)", source: "WRDS fundq · oancfy", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "investing_cash_flow", type: "float64 (T,N)", source: "WRDS fundq · ivncfy", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "shares_outstanding", type: "float64 (T,N)", source: "WRDS fundq · cshoq", coverage: "quarterly" },
  { group: "FUNDAMENTALS", name: "total_liabilities", type: "float64 (T,N)", source: "WRDS fundq · ltq", coverage: "quarterly" },
  // INSIDER — Form 4 alt-alpha
  { group: "INSIDER", name: "insider_net_dollars", type: "float64 (T,N)", source: "SEC EDGAR Form 4 (signed P-S $)", coverage: "sparse" },
  { group: "INSIDER", name: "insider_n_buys", type: "float64 (T,N)", source: "SEC EDGAR Form 4 (P count)", coverage: "sparse" },
  { group: "INSIDER", name: "insider_n_sells", type: "float64 (T,N)", source: "SEC EDGAR Form 4 (S count)", coverage: "sparse" },
  // MASKS
  { group: "MASKS", name: "is_member", type: "bool (T,N)", source: "fja05680/sp500 historical CSV", coverage: "full" },
  // BENCHMARKS
  { group: "BENCHMARKS", name: "benchmark_close", type: "float64 (T,)", source: "SPY (default)", coverage: "full" },
  { group: "BENCHMARKS", name: "benchmark_alts", type: "dict[str, (T,)]", source: "{SPY, RSP}", coverage: "full" },
];

/* ── Backtest metric categorization ───────────────────────────────── */

type MetricCategory = "BASE" | "IC" | "SIG" | "OVERFIT" | "COST" | "REGIME";

interface MetricRow {
  readonly category: MetricCategory;
  readonly keyBase: string;
  readonly formula: string;
  readonly ref: string;
}

const METRIC_ROWS: readonly MetricRow[] = [
  { category: "BASE", keyBase: "sharpe", formula: "Sharpe = mean(daily_ret) / std(daily_ret) × √252", ref: "factor_backtest.py:_split_metrics" },
  { category: "BASE", keyBase: "totalReturn", formula: "Total return = ∏(1 + daily_ret) − 1 over the slice", ref: "factor_backtest.py:_split_metrics" },
  { category: "IC", keyBase: "ic", formula: "IC = mean of cross-sectional Spearman(rank(factor[t]), rank(fwd_ret[t])) across t", ref: "kernel.py:spearman_ic" },
  { category: "BASE", keyBase: "mdd", formula: "MaxDD = min((cumprod(1+r) − running_max) / running_max)", ref: "factor_backtest.py:_max_drawdown" },
  { category: "BASE", keyBase: "turnover", formula: "Turnover = mean(L1 norm of weight delta between consecutive rows)", ref: "factor_backtest.py:_split_metrics" },
  { category: "BASE", keyBase: "hitRate", formula: "Hit rate = fraction of days with daily IC > 0", ref: "factor_backtest.py:_split_metrics" },
  { category: "IC", keyBase: "icir", formula: "ICIR = mean(IC) / std(IC) × √252", ref: "factor_backtest.py:_split_metrics" },
  { category: "SIG", keyBase: "icPvalue", formula: "IC p = math.erfc(|t| / √2) where t = mean(IC) / (std(IC)/√n)", ref: "factor_backtest.py:_split_metrics" },
  { category: "SIG", keyBase: "psr", formula: "PSR = Φ((SR − E[max SR | SR=0, n_trials]) × √(n−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²))", ref: "scan/significance.py:deflated_sharpe" },
  { category: "BASE", keyBase: "alphaBeta", formula: "α + β = OLS regress(daily_ret, bench_daily); α-t and α-p reported", ref: "factor_engine/risk_attribution.py" },
  { category: "SIG", keyBase: "bootstrapCi", formula: "95% CI via stationary block bootstrap (block_len=20, n_resamples=1000)", ref: "scan/significance.py:stationary_block_bootstrap_ci" },
  { category: "OVERFIT", keyBase: "overfitFlag", formula: "overfit = (train_SR > 0.5) AND ((train_SR − test_SR)/train_SR > 0.5)", ref: "factor_backtest.py:run_factor_backtest" },
  { category: "COST", keyBase: "slippageCost", formula: "slippage_bps = bps_const + k × √(participation/ADV) per trade", ref: "factor_backtest.py:run_factor_backtest" },
  { category: "COST", keyBase: "borrowCost", formula: "borrow_drag = short_borrow_bps/252 × Σ|w_short| each day", ref: "factor_backtest.py:run_factor_backtest" },
  { category: "REGIME", keyBase: "regime", formula: "Days classified by SPY 60d return: bull >+5%, bear <−5%, sideways otherwise; SR/IC/α reported per regime", ref: "factor_backtest.py:_classify_regimes" },
];

/* ── Page ─────────────────────────────────────────────────────────── */

export default function MethodologyPage() {
  const { locale } = useLocale();
  const [tab, setTab] = useState<Tab>("data");
  const [universes, setUniverses] = useState<UniverseListResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [sectors, setSectors] = useState<readonly string[]>([]);
  const [catalog, setCatalog] = useState<OperandCatalogResponse | null>(null);
  const [universesError, setUniversesError] = useState<string | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [sectorsError, setSectorsError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const [loadStartedAt] = useState<number>(() => Date.now());
  const [loadFinishedAt, setLoadFinishedAt] = useState<number | null>(null);

  const loadDataTab = useCallback(async (force = false) => {
    setReloading(true);
    if (force) invalidateDataCache();
    setUniversesError(null);
    setCoverageError(null);
    setSectorsError(null);
    const t0 = Date.now();
    const [u, c, s] = await Promise.all([
      fetchUniverses({ force }),
      fetchCoverage("SP500_subset", { force }),
      fetchSectors(),
    ]);
    if (u.error) setUniversesError(u.error);
    else if (u.data) setUniverses(u.data);
    if (c.error) setCoverageError(c.error);
    else if (c.data) setCoverage(c.data);
    if (s.error) setSectorsError(s.error);
    else if (s.data) setSectors(s.data.sectors);
    setLoadFinishedAt(Date.now());
    void t0;
    setReloading(false);
  }, []);

  const loadOperatorsTab = useCallback(async () => {
    setReloading(true);
    setCatalogError(null);
    const r = await fetchOperandCatalogWithSignatures();
    if (r.error) setCatalogError(r.error);
    else if (r.data) setCatalog(r.data);
    setReloading(false);
  }, []);

  useEffect(() => {
    void loadDataTab(false);
  }, [loadDataTab]);

  useEffect(() => {
    if (tab !== "operators" || catalog !== null) return;
    void loadOperatorsTab();
  }, [tab, catalog, loadOperatorsTab]);

  const dataTabHasError = Boolean(
    universesError || coverageError || sectorsError,
  );
  const dataErrors = [universesError, coverageError, sectorsError].filter(
    Boolean,
  ) as string[];
  const loadMs =
    loadFinishedAt !== null ? loadFinishedAt - loadStartedAt : null;

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">METHODOLOGY</span>
        <TmSubbarSep />
        {(["data", "operators", "backtest"] as Tab[]).map((tk) => (
          <TmChip key={tk} on={tab === tk} onClick={() => setTab(tk)}>
            {t(locale, `methodology.tab.${tk}` as Parameters<typeof t>[1])}
          </TmChip>
        ))}
        <TmSubbarSpacer />
        {tab === "data" && universes && (
          <>
            <TmSubbarKV
              label="N"
              value={universes.universes[0]?.ticker_count ?? "—"}
            />
            <TmSubbarSep />
            <TmSubbarKV label="FIELDS" value={PANEL_SCHEMA.length} />
            <TmSubbarSep />
          </>
        )}
        {tab === "operators" && catalog && (
          <>
            <TmSubbarKV
              label="OPS"
              value={`${(catalog.operators as OperatorWithSignature[]).filter((o) => o.implemented).length}/${catalog.operators.length}`}
            />
            <TmSubbarSep />
          </>
        )}
        {tab === "backtest" && (
          <>
            <TmSubbarKV label="METRICS" value={METRIC_ROWS.length} />
            <TmSubbarSep />
          </>
        )}
        {tab === "data" && dataTabHasError && (
          <TmStatusPill tone="err">FETCH ERROR</TmStatusPill>
        )}
        {tab === "operators" && catalogError && (
          <TmStatusPill tone="err">FETCH ERROR</TmStatusPill>
        )}
        {tab === "data" && (
          <TmButton
            variant="ghost"
            onClick={() => loadDataTab(true)}
            disabled={reloading}
            className="-my-1 px-2"
          >
            {reloading
              ? t(locale, "methodology.retrying")
              : t(locale, "methodology.retry")}
          </TmButton>
        )}
        {tab === "operators" && (
          <TmButton
            variant="ghost"
            onClick={loadOperatorsTab}
            disabled={reloading}
            className="-my-1 px-2"
          >
            {reloading
              ? t(locale, "methodology.retrying")
              : t(locale, "methodology.retry")}
          </TmButton>
        )}
      </TmSubbar>

      {tab === "data" && dataTabHasError && (
        <ErrorPane
          title={t(locale, "methodology.error")}
          messages={dataErrors}
        />
      )}
      {tab === "operators" && catalogError && (
        <ErrorPane
          title={t(locale, "methodology.error")}
          messages={[catalogError]}
        />
      )}

      {tab === "data" && (
        <DataTab
          universes={universes}
          coverage={coverage}
          sectors={sectors}
          loadMs={loadMs}
        />
      )}
      {tab === "operators" && <OperatorsTab catalog={catalog} />}
      {tab === "backtest" && <BacktestTab />}
    </TmScreen>
  );
}

/* ── Data tab ─────────────────────────────────────────────────────── */

function DataTab({
  universes,
  coverage,
  sectors,
  loadMs,
}: {
  readonly universes: UniverseListResponse | null;
  readonly coverage: CoverageResponse | null;
  readonly sectors: readonly string[];
  readonly loadMs: number | null;
}) {
  const { locale } = useLocale();
  const u = universes?.universes[0];

  if (!u || !coverage) {
    return (
      <TmPane title="PANEL.OVERVIEW">
        <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "common.loading")}
        </p>
      </TmPane>
    );
  }

  return (
    <>
      {/* 8-cell KPI strip */}
      <TmPane
        title="PANEL.OVERVIEW"
        meta={`${u.id} · ${u.benchmark} · ${u.currency}`}
      >
        <TmKpiGrid>
          <TmKpi label="TICKERS" value={u.ticker_count.toString()} sub={u.id} />
          <TmKpi
            label="N_DAYS"
            value={u.n_days.toString()}
            sub={`${u.start_date} → ${u.end_date}`}
          />
          <TmKpi
            label="OHLCV %"
            value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`}
            tone={coverage.ohlcv_coverage_pct >= 99 ? "pos" : "warn"}
            sub="non-NaN cells"
          />
          <TmKpi label="BENCHMARK" value={u.benchmark} sub={u.currency} />
          <TmKpi label="SECTORS" value={sectors.length.toString()} sub="GICS-1" />
          <TmKpi
            label="FIELDS"
            value={PANEL_SCHEMA.length.toString()}
            sub="schema cols"
          />
          <TmKpi
            label="LOAD_MS"
            value={loadMs !== null ? loadMs.toString() : "—"}
            sub="last fetch"
          />
          <TmKpi label="UNIVERSE" value={u.name} />
        </TmKpiGrid>
      </TmPane>

      {/* 2-col: Pipeline (left) | Sectors + BiasGuards (right stacked) */}
      <TmCols2>
        <TmPane title="DATA.PIPELINE" meta="5 STAGES">
          <ol className="flex flex-col">
            {[1, 2, 3, 4, 5].map((n) => (
              <li
                key={n}
                className="flex gap-3 border-b border-tm-rule px-3 py-2 font-tm-mono text-[11px] leading-relaxed text-tm-fg last:border-b-0"
              >
                <span className="shrink-0 text-tm-accent">
                  {String(n).padStart(2, "0")}
                </span>
                <span>
                  {t(
                    locale,
                    `methodology.data.step${n}` as Parameters<typeof t>[1],
                  )}
                </span>
              </li>
            ))}
          </ol>
        </TmPane>

        <div className="flex flex-col [&>*:not(:last-child)]:border-b [&>*:not(:last-child)]:border-tm-rule">
          <TmPane title="AVAILABLE.SECTORS" meta={`${sectors.length} GICS-1`}>
            <p className="px-3 pt-2.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
              {t(locale, "methodology.data.sectorsSubtitle")}
            </p>
            <div className="flex flex-wrap gap-1.5 px-3 pb-3 pt-2">
              {sectors.map((s) => (
                <span
                  key={s}
                  className="border border-tm-rule bg-tm-bg-2 px-2 py-px font-tm-mono text-[10.5px] text-tm-fg-2"
                >
                  {s}
                </span>
              ))}
            </div>
          </TmPane>

          <TmPane title="BIAS.GUARDS" meta="2 INVARIANTS">
            <ul className="flex flex-col">
              <li className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg">
                <span className="text-tm-accent">▸ Survivorship</span>
                <span className="ml-2 text-tm-muted">
                  is_member mask (T,N) → non-member cells NaN
                </span>
                <div className="mt-1 text-tm-fg-2">
                  evaluate_factor_full enforces is_member at evaluation time;
                  factors never see a ticker on days it was not in the index,
                  even if its OHLCV row exists in the parquet.
                </div>
              </li>
              <li className="px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg">
                <span className="text-tm-accent">▸ Lookahead</span>
                <span className="ml-2 text-tm-muted">
                  RDQ ≤ t PIT join on fundq
                </span>
                <div className="mt-1 text-tm-fg-2">
                  fundamentals_pit_sp500_v3 keys on RDQ (filing date), not
                  fiscal-period-end. Each (t, ticker) sees only quarters whose
                  filing landed by t. Forward-fill is disabled; algos see NaN
                  before the first filing.
                </div>
              </li>
            </ul>
          </TmPane>
        </div>
      </TmCols2>

      {/* Full-width schema table */}
      <TmPane
        title="PANEL.SCHEMA"
        meta={`${PANEL_SCHEMA.length} FIELDS · 6 GROUPS`}
      >
        <div
          className="grid gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(110px, 130px) minmax(150px, 180px) minmax(120px, 140px) 1fr minmax(80px, 100px)",
          }}
        >
          <SchemaHeader>GROUP</SchemaHeader>
          <SchemaHeader>FIELD</SchemaHeader>
          <SchemaHeader>TYPE</SchemaHeader>
          <SchemaHeader>SOURCE</SchemaHeader>
          <SchemaHeader>COVERAGE</SchemaHeader>
          {PANEL_SCHEMA.map((f) => (
            <SchemaRow key={f.name} field={f} />
          ))}
        </div>
      </TmPane>
    </>
  );
}

function SchemaHeader({ children }: { readonly children: React.ReactNode }) {
  return (
    <div className="bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
      {children}
    </div>
  );
}

function SchemaRow({ field }: { readonly field: SchemaField }) {
  const groupTone =
    field.group === "PRICES"
      ? "text-tm-accent"
      : field.group === "FUNDAMENTALS"
        ? "text-tm-info"
        : field.group === "INSIDER"
          ? "text-tm-warn"
          : field.group === "MASKS"
            ? "text-tm-pos"
            : field.group === "BENCHMARKS"
              ? "text-tm-fg"
              : "text-tm-fg-2";
  const covTone =
    field.coverage === "full"
      ? "text-tm-pos"
      : field.coverage === "sparse"
        ? "text-tm-warn"
        : field.coverage === "snapshot"
          ? "text-tm-muted"
          : "text-tm-info";
  return (
    <>
      <div className={`bg-tm-bg px-3 py-1 font-tm-mono text-[10.5px] ${groupTone}`}>
        {field.group}
      </div>
      <div className="bg-tm-bg px-3 py-1 font-tm-mono text-[11px] text-tm-fg">
        {field.name}
      </div>
      <div className="bg-tm-bg px-3 py-1 font-tm-mono text-[10.5px] text-tm-fg-2">
        {field.type}
      </div>
      <div className="bg-tm-bg px-3 py-1 font-tm-mono text-[10.5px] text-tm-muted">
        {field.source}
      </div>
      <div className={`bg-tm-bg px-3 py-1 font-tm-mono text-[10.5px] ${covTone}`}>
        {field.coverage}
      </div>
    </>
  );
}

/* ── Operators tab ────────────────────────────────────────────────── */

function OperatorsTab({
  catalog,
}: {
  readonly catalog: OperandCatalogResponse | null;
}) {
  const { locale } = useLocale();
  const [catFilter, setCatFilter] = useState<string>("all");
  const [tierFilter, setTierFilter] = useState<string>("all");

  if (!catalog) {
    return (
      <TmPane title="OPS.OVERVIEW">
        <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "common.loading")}
        </p>
      </TmPane>
    );
  }
  const ops = catalog.operators as OperatorWithSignature[];
  const implemented = ops.filter((o) => o.implemented);

  const categories = Array.from(
    new Set(implemented.map((o) => o.category ?? "uncategorized")),
  ).sort();
  const tiers = Array.from(
    new Set(implemented.map((o) => o.tier ?? "T1")),
  ).sort();

  const filtered = implemented.filter((o) => {
    const cat = o.category ?? "uncategorized";
    const tier = o.tier ?? "T1";
    if (catFilter !== "all" && cat !== catFilter) return false;
    if (tierFilter !== "all" && tier !== tierFilter) return false;
    return true;
  });

  return (
    <>
      <TmPane
        title="OPS.OVERVIEW"
        meta={`${implemented.length} / ${ops.length} IMPLEMENTED`}
      >
        <TmKpiGrid>
          <TmKpi label="TOTAL" value={ops.length.toString()} sub="registered" />
          <TmKpi
            label="IMPL"
            value={implemented.length.toString()}
            tone="pos"
            sub="callable"
          />
          <TmKpi
            label="CATEGORIES"
            value={categories.length.toString()}
            sub="op groups"
          />
          <TmKpi
            label="TIERS"
            value={tiers.length.toString()}
            sub={tiers.join(" · ")}
          />
        </TmKpiGrid>
        <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
          {t(locale, "methodology.operators.subtitle")
            .replace("{n}", String(implemented.length))
            .replace("{total}", String(ops.length))}
        </p>
      </TmPane>

      <TmPane
        title="OPS.CATALOG"
        meta={`${filtered.length} SHOWN`}
      >
        {/* Filter chips */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
          <span className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            CATEGORY
          </span>
          <TmChip on={catFilter === "all"} onClick={() => setCatFilter("all")}>
            all
          </TmChip>
          {categories.map((c) => (
            <TmChip
              key={c}
              on={catFilter === c}
              onClick={() => setCatFilter(c)}
            >
              {c}
            </TmChip>
          ))}
          <span className="ml-3 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            TIER
          </span>
          <TmChip
            on={tierFilter === "all"}
            onClick={() => setTierFilter("all")}
          >
            all
          </TmChip>
          {tiers.map((t_) => (
            <TmChip
              key={t_}
              on={tierFilter === t_}
              onClick={() => setTierFilter(t_)}
            >
              {t_}
            </TmChip>
          ))}
        </div>

        {/* Flat hairline list */}
        <ul className="flex flex-col">
          {filtered.map((op) => (
            <li
              key={op.name}
              className="border-b border-tm-rule last:border-b-0"
            >
              <details className="group">
                <summary className="flex cursor-pointer items-center gap-3 px-3 py-1.5 font-tm-mono text-[11px] hover:bg-tm-bg-2">
                  <span className="text-tm-muted group-open:text-tm-accent">
                    {">"}
                  </span>
                  <span className="flex-1 text-tm-accent">
                    {op.signature ?? op.name}
                  </span>
                  <span className="text-tm-fg-2">{op.category ?? "—"}</span>
                  <span className="text-tm-muted">·</span>
                  <span className="w-6 text-tm-muted">{op.tier ?? "T1"}</span>
                </summary>
                {op.source_snippet && (
                  <pre className="m-0 overflow-x-auto border-t border-tm-rule bg-tm-bg-2 px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
                    {op.source_snippet}
                  </pre>
                )}
              </details>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
              no operators match the filter.
            </li>
          )}
        </ul>
      </TmPane>
    </>
  );
}

/* ── Backtest tab ─────────────────────────────────────────────────── */

function BacktestTab() {
  const { locale } = useLocale();
  const [catFilter, setCatFilter] = useState<MetricCategory | "all">("all");

  const categoryCounts = useMemo(() => {
    const counts = new Map<MetricCategory, number>();
    for (const r of METRIC_ROWS) {
      counts.set(r.category, (counts.get(r.category) ?? 0) + 1);
    }
    return counts;
  }, []);

  const filtered = METRIC_ROWS.filter(
    (r) => catFilter === "all" || r.category === catFilter,
  );

  const sourceFiles = new Set(METRIC_ROWS.map((r) => r.ref.split(":")[0]));

  return (
    <>
      <TmPane
        title="METRICS.OVERVIEW"
        meta={`${METRIC_ROWS.length} METRICS · ${categoryCounts.size} CATEGORIES`}
      >
        <TmKpiGrid>
          <TmKpi
            label="METRICS"
            value={METRIC_ROWS.length.toString()}
            sub="total formulas"
          />
          <TmKpi
            label="CATEGORIES"
            value={categoryCounts.size.toString()}
            sub="metric groups"
          />
          <TmKpi
            label="SOURCE_FILES"
            value={sourceFiles.size.toString()}
            sub="impl modules"
          />
          <TmKpi
            label="ALPHA_LAYER"
            value="OLS"
            tone="pos"
            sub="α/β + bootstrap"
          />
        </TmKpiGrid>
        <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
          {t(locale, "methodology.backtest.subtitle")}
        </p>
      </TmPane>

      <TmPane
        title="METRICS.CATALOG"
        meta={`${filtered.length} SHOWN`}
      >
        <div className="flex flex-wrap items-center gap-1.5 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5">
          <span className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            CATEGORY
          </span>
          <TmChip
            on={catFilter === "all"}
            onClick={() => setCatFilter("all")}
            count={METRIC_ROWS.length}
          >
            all
          </TmChip>
          {(["BASE", "IC", "SIG", "OVERFIT", "COST", "REGIME"] as MetricCategory[]).map(
            (c) => (
              <TmChip
                key={c}
                on={catFilter === c}
                onClick={() => setCatFilter(c)}
                count={categoryCounts.get(c) ?? 0}
              >
                {c}
              </TmChip>
            ),
          )}
        </div>

        <div
          className="grid gap-px bg-tm-rule"
          style={{
            gridTemplateColumns:
              "minmax(80px, 100px) minmax(140px, 180px) 1fr minmax(180px, 220px)",
          }}
        >
          <SchemaHeader>CAT</SchemaHeader>
          <SchemaHeader>{t(locale, "methodology.backtest.colMetric")}</SchemaHeader>
          <SchemaHeader>{t(locale, "methodology.backtest.colFormula")}</SchemaHeader>
          <SchemaHeader>{t(locale, "methodology.backtest.colRef")}</SchemaHeader>
          {filtered.map((r) => (
            <MetricGridRow key={r.keyBase} row={r} />
          ))}
        </div>
      </TmPane>

      <TmPane
        title="PORTFOLIO.RULES"
        meta="4 RULES"
      >
        <ul className="flex flex-col">
          {[1, 2, 3, 4].map((n) => (
            <li
              key={n}
              className="flex gap-3 border-b border-tm-rule px-3 py-2 font-tm-mono text-[11px] leading-relaxed text-tm-fg last:border-b-0"
            >
              <span className="shrink-0 text-tm-accent">·</span>
              <span>
                {t(
                  locale,
                  `methodology.backtest.portfolio${n}` as Parameters<typeof t>[1],
                )}
              </span>
            </li>
          ))}
        </ul>
      </TmPane>
    </>
  );
}

function MetricGridRow({ row }: { readonly row: MetricRow }) {
  const { locale } = useLocale();
  const catTone =
    row.category === "BASE"
      ? "text-tm-fg"
      : row.category === "IC"
        ? "text-tm-info"
        : row.category === "SIG"
          ? "text-tm-accent"
          : row.category === "OVERFIT"
            ? "text-tm-warn"
            : row.category === "COST"
              ? "text-tm-neg"
              : "text-tm-pos";
  return (
    <>
      <div className={`bg-tm-bg px-3 py-1.5 font-tm-mono text-[10.5px] ${catTone}`}>
        {row.category}
      </div>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[11px] text-tm-accent">
        {t(locale, `methodology.backtest.${row.keyBase}` as Parameters<typeof t>[1])}
      </div>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg">
        {row.formula}
      </div>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-muted">
        {row.ref}
      </div>
    </>
  );
}

/* ── Helpers ──────────────────────────────────────────────────────── */

function ErrorPane({
  title,
  messages,
}: {
  readonly title: string;
  readonly messages: readonly string[];
}) {
  // Dedupe — when multiple parallel fetches hit the same edge IP poisoning
  // they often produce the identical TypeError text; one row is plenty.
  const unique = Array.from(new Set(messages));
  return (
    <TmPane
      title={title}
      meta={`${unique.length} ISSUE${unique.length === 1 ? "" : "S"}`}
    >
      <ul className="flex flex-col">
        {unique.map((m, i) => (
          <li
            key={i}
            className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[11px] leading-relaxed text-tm-neg last:border-b-0"
          >
            {m}
          </li>
        ))}
      </ul>
    </TmPane>
  );
}
