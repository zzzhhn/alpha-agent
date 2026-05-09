"use client";

/**
 * Methodology page — workstation port (Stage 3 · 3/9).
 *
 * Surfaces three tabs explaining how the platform actually works:
 *   - DATA: which universe, which fields, which pipeline steps
 *   - OPERATORS: every implemented op with signature + source snippet
 *   - BACKTEST: every reported metric with formula + source ref
 *
 * Layout uses the workstation primitives. TmSubbar carries the active-tab
 * chip row + retry control. Each pane is flat and edge-to-edge with the
 * shared bottom hairline. Data tab leads with a 5-cell TmKpiGrid +
 * sectors chips + numbered pipeline. Operators tab keeps the per-op
 * `<details>` disclosure but in flat hairline rows. Backtest tab keeps
 * the formula table but as a hairline-grid (`gap-px bg-tm-rule`) instead
 * of legacy alternating zebra.
 *
 * Per-fetch error tracking + targeted retry preserved from legacy.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
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

  const loadDataTab = useCallback(async (force = false) => {
    setReloading(true);
    if (force) invalidateDataCache();
    setUniversesError(null);
    setCoverageError(null);
    setSectorsError(null);
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
            <TmSubbarKV label="N" value={universes.universes[0]?.ticker_count ?? "—"} />
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
        <DataTab universes={universes} coverage={coverage} sectors={sectors} />
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
}: {
  readonly universes: UniverseListResponse | null;
  readonly coverage: CoverageResponse | null;
  readonly sectors: readonly string[];
}) {
  const { locale } = useLocale();
  const u = universes?.universes[0];

  if (!u || !coverage) {
    return (
      <TmPane title={t(locale, "methodology.data.panelTitle")}>
        <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "common.loading")}
        </p>
      </TmPane>
    );
  }

  return (
    <>
      <TmPane
        title={t(locale, "methodology.data.panelTitle")}
        meta={`${u.id} · ${u.benchmark}`}
      >
        <TmKpiGrid>
          <TmKpi
            label={t(locale, "methodology.data.tickers")}
            value={u.ticker_count.toString()}
            sub={u.id}
          />
          <TmKpi
            label={t(locale, "methodology.data.days")}
            value={u.n_days.toString()}
            sub={`${u.start_date} → ${u.end_date}`}
          />
          <TmKpi
            label={t(locale, "methodology.data.ohlcvCoverage")}
            value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`}
            tone={coverage.ohlcv_coverage_pct >= 99 ? "pos" : "warn"}
            sub="OHLCV"
          />
          <TmKpi
            label={t(locale, "methodology.data.benchmark")}
            value={u.benchmark}
            sub={u.currency}
          />
          <TmKpi
            label={t(locale, "methodology.data.universe")}
            value={u.name}
          />
        </TmKpiGrid>
      </TmPane>

      <TmPane
        title={t(locale, "methodology.data.sectorsTitle")}
        meta={`${sectors.length} GICS-1`}
      >
        <p className="px-3 pt-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
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

      <TmPane
        title={t(locale, "methodology.data.pipelineTitle")}
        meta="5 STAGES"
      >
        <ol className="flex flex-col">
          {[1, 2, 3, 4, 5].map((n) => (
            <li
              key={n}
              className="flex gap-3 border-b border-tm-rule px-3 py-2 font-tm-mono text-[11px] leading-relaxed text-tm-fg last:border-b-0"
            >
              <span className="shrink-0 text-tm-accent">
                {String(n).padStart(2, "0")}
              </span>
              <span className="text-tm-fg">
                {t(
                  locale,
                  `methodology.data.step${n}` as Parameters<typeof t>[1],
                )}
              </span>
            </li>
          ))}
        </ol>
      </TmPane>
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
  if (!catalog) {
    return (
      <TmPane title={t(locale, "methodology.operators.title")}>
        <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "common.loading")}
        </p>
      </TmPane>
    );
  }
  const ops = catalog.operators as OperatorWithSignature[];
  const implemented = ops.filter((o) => o.implemented);
  const byCategory = new Map<string, OperatorWithSignature[]>();
  for (const op of implemented) {
    const cat = op.category ?? "uncategorized";
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat)!.push(op);
  }

  return (
    <>
      <TmPane
        title={t(locale, "methodology.operators.title")}
        meta={`${implemented.length}/${ops.length} IMPLEMENTED`}
      >
        <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
          {t(locale, "methodology.operators.subtitle")
            .replace("{n}", String(implemented.length))
            .replace("{total}", String(ops.length))}
        </p>
      </TmPane>

      {Array.from(byCategory.entries())
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([cat, list]) => (
          <TmPane key={cat} title={cat} meta={`${list.length}`}>
            <ul className="flex flex-col">
              {list.map((op) => (
                <li
                  key={op.name}
                  className="border-b border-tm-rule last:border-b-0"
                >
                  <details className="group">
                    <summary className="cursor-pointer px-3 py-1.5 font-tm-mono text-[11.5px] text-tm-fg hover:bg-tm-bg-2">
                      <span className="text-tm-muted group-open:text-tm-accent">
                        {">"}{" "}
                      </span>
                      <span className="text-tm-accent">{op.signature ?? op.name}</span>
                    </summary>
                    {op.source_snippet && (
                      <pre className="m-0 overflow-x-auto border-t border-tm-rule bg-tm-bg-2 px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
                        {op.source_snippet}
                      </pre>
                    )}
                  </details>
                </li>
              ))}
            </ul>
          </TmPane>
        ))}
    </>
  );
}

/* ── Backtest tab ─────────────────────────────────────────────────── */

function BacktestTab() {
  const { locale } = useLocale();

  // Each row documents one engine output. v4 surfaced 9 additional rigor
  // metrics on top of the 6 base KPIs; these are spelled out so users can
  // see the formulas and find the source via the ref column.
  const rows: { keyBase: string; formula: string; ref: string }[] = [
    { keyBase: "sharpe", formula: "Sharpe = mean(daily_ret) / std(daily_ret) × √252", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "totalReturn", formula: "Total return = ∏(1 + daily_ret) − 1 over the slice", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "ic", formula: "IC = mean of cross-sectional Spearman(rank(factor[t]), rank(fwd_ret[t])) across t", ref: "kernel.py:spearman_ic" },
    { keyBase: "mdd", formula: "MaxDD = min((cumprod(1+r) − running_max) / running_max)", ref: "factor_backtest.py:_max_drawdown" },
    { keyBase: "turnover", formula: "Turnover = mean(L1 norm of weight delta between consecutive rows)", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "hitRate", formula: "Hit rate = fraction of days with daily IC > 0", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "icir", formula: "ICIR = mean(IC) / std(IC) × √252", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "icPvalue", formula: "IC p = math.erfc(|t| / √2) where t = mean(IC) / (std(IC)/√n)", ref: "factor_backtest.py:_split_metrics" },
    { keyBase: "psr", formula: "PSR = Φ((SR − E[max SR | SR=0, n_trials]) × √(n−1) / √(1 − γ₃·SR + (γ₄−1)/4·SR²))", ref: "scan/significance.py:deflated_sharpe" },
    { keyBase: "alphaBeta", formula: "α + β = OLS regress(daily_ret, bench_daily); α-t and α-p reported", ref: "factor_engine/risk_attribution.py" },
    { keyBase: "bootstrapCi", formula: "95% CI via stationary block bootstrap (block_len=20, n_resamples=1000)", ref: "scan/significance.py:stationary_block_bootstrap_ci" },
    { keyBase: "overfitFlag", formula: "overfit = (train_SR > 0.5) AND ((train_SR − test_SR)/train_SR > 0.5)", ref: "factor_backtest.py:run_factor_backtest" },
    { keyBase: "slippageCost", formula: "slippage_bps = bps_const + k × √(participation/ADV) per trade", ref: "factor_backtest.py:run_factor_backtest" },
    { keyBase: "borrowCost", formula: "borrow_drag = short_borrow_bps/252 × Σ|w_short| each day", ref: "factor_backtest.py:run_factor_backtest" },
    { keyBase: "regime", formula: "Days classified by SPY 60d return: bull >+5%, bear <−5%, sideways otherwise; SR/IC/α reported per regime", ref: "factor_backtest.py:_classify_regimes" },
  ];

  return (
    <>
      <TmPane
        title={t(locale, "methodology.backtest.title")}
        meta={`${rows.length} METRICS`}
      >
        <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
          {t(locale, "methodology.backtest.subtitle")}
        </p>
      </TmPane>

      <TmPane
        title={t(locale, "methodology.backtest.kpiTitle")}
        meta="FORMULA · SOURCE"
      >
        <div
          className="grid gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "minmax(140px, 180px) 1fr minmax(180px, 240px)" }}
        >
          <div className="bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "methodology.backtest.colMetric")}
          </div>
          <div className="bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "methodology.backtest.colFormula")}
          </div>
          <div className="bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "methodology.backtest.colRef")}
          </div>
          {rows.map((r) => (
            <BacktestRow key={r.keyBase} keyBase={r.keyBase} formula={r.formula} ref_={r.ref} />
          ))}
        </div>
      </TmPane>

      <TmPane
        title={t(locale, "methodology.backtest.portfolioTitle")}
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

function BacktestRow({
  keyBase,
  formula,
  ref_,
}: {
  readonly keyBase: string;
  readonly formula: string;
  readonly ref_: string;
}) {
  const { locale } = useLocale();
  return (
    <>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[11px] text-tm-accent">
        {t(locale, `methodology.backtest.${keyBase}` as Parameters<typeof t>[1])}
      </div>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg">
        {formula}
      </div>
      <div className="bg-tm-bg px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-muted">
        {ref_}
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
    <TmPane title={title} meta={`${unique.length} ISSUE${unique.length === 1 ? "" : "S"}`}>
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
