"use client";

import { useCallback, useEffect, useId, useState, type ReactNode } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmCols2, TmPane, TmScreen } from "@/components/tm/TmPane";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmChip, TmStatusPill, TmSubbar, TmSubbarSpacer } from "@/components/tm/TmSubbar";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import {
  fetchCoverage,
  fetchOperandCatalogWithSignatures,
  fetchSectors,
  fetchUniverses,
  invalidateDataCache,
} from "@/lib/api";
import { t } from "@/lib/i18n";
import { sectorLabel } from "@/lib/sector-label";
import type { CoverageResponse, OperandCatalogResponse, OperatorInfo, UniverseListResponse } from "@/lib/types";

type Tab = "data" | "operators" | "backtest" | "evidence";
type OperatorWithSignature = OperatorInfo & { readonly source_snippet?: string };
type LocalText = { readonly zh: string; readonly en: string };
const text = (zh: string, en: string): LocalText => ({ zh, en });

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

const TABS = ["data", "operators", "backtest", "evidence"] as const;
const UNIVERSE_ID = "SP500_subset";
const PAGE_SIZE = 10;

const SCHEMA_GROUPS: Record<SchemaField["group"], LocalText> = {
  PRICES: text("行情", "Prices"),
  META: text("标的属性", "Security metadata"),
  FUNDAMENTALS: text("财务数据", "Fundamentals"),
  INSIDER: text("内部人交易", "Insider trades"),
  MASKS: text("成员范围", "Membership"),
  BENCHMARKS: text("基准", "Benchmarks"),
};

const SCHEMA_PATTERNS: Record<SchemaField["coverage"], LocalText> = {
  full: text("面板对齐", "Panel-aligned"),
  sparse: text("事件型，分布稀疏", "Sparse events"),
  quarterly: text("季度披露", "Quarterly filings"),
  snapshot: text("属性快照", "Metadata snapshot"),
};

const METRIC_GROUPS: Record<MetricCategory, LocalText> = {
  BASE: text("组合表现", "Performance"),
  IC: text("因子预测力", "Predictive power"),
  SIG: text("统计检验", "Significance"),
  OVERFIT: text("过拟合", "Overfitting"),
  COST: text("交易成本", "Trading costs"),
  REGIME: text("市场状态", "Market regimes"),
};

const OPERATOR_GROUPS: Record<string, LocalText> = {
  arithmetic: text("算术", "Arithmetic"),
  cross_section: text("横截面", "Cross-sectional"),
  group: text("分组", "Group"),
  logical: text("逻辑", "Logic"),
  time_series: text("时间序列", "Time series"),
  transformational: text("变换", "Transformations"),
  vector: text("向量", "Vector"),
  uncategorized: text("未分类", "Uncategorized"),
};

const PIPELINE = [
  { label: text("准备历史行情", "Build the price history"), description: text("从历史 S&P 500 成员名单取标的并集（含已退市标的），再由 Alpaca 提取日线 OHLCV。", "Build the ticker union from historical S&P 500 membership, including delisted names, then pull daily OHLCV from Alpaca."), source: "scripts/fetch_sp500_alpaca.py → factor_universe_sp500_v3.parquet" },
  { label: text("按披露日对齐财报", "Join financials by disclosure date"), description: text("WRDS Compustat 季报按披露日（RDQ）对齐。每个交易日只使用当日或此前已披露的报告。", "Join WRDS Compustat quarterly reports by disclosure date (RDQ). Each trading day can use only reports disclosed by that day."), source: "scripts/build_pit_fundamentals_wrds.py → fundamentals_pit_sp500_v3.parquet" },
  { label: text("限制每日成分股范围", "Apply daily index membership"), description: text("用 is_member 标记当日成分股。即使面板保存了行情，非成员单元格也不参与该日因子评估。", "Use is_member to mask out nonmembers on each date, even if the panel has prices for those tickers."), source: "alpha_agent/data/membership.py · evaluate_factor_full" },
  { label: text("对齐数据面板", "Align the panel"), description: text("行情、标的属性、财务数据、成员范围和基准共用一条日期轴，面板由服务读取并缓存。", "The service loads and caches prices, security metadata, financials, membership and benchmarks on a shared date axis."), source: "_Panel · benchmark_alts={SPY, RSP}" },
  { label: text("检查交易日与缺值", "Check trading dates and missing data"), description: text("用 NYSE 交易日历校验日期。缺失行情保留为 NaN，不用前值补齐。", "Validate dates against the NYSE calendar. Missing prices stay NaN rather than being filled forward."), source: "_assert_trading_days() · DataIntegrityError" },
] as const;

export default function MethodologyPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [tab, setTab] = useState<Tab>("data");
  const [universes, setUniverses] = useState<UniverseListResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [sectors, setSectors] = useState<readonly string[] | null>(null);
  const [catalog, setCatalog] = useState<OperandCatalogResponse | null>(null);
  const [dataErrors, setDataErrors] = useState<readonly string[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const loadDataTab = useCallback(async (force = false) => {
    setDataLoading(true);
    setDataErrors([]);
    if (force) invalidateDataCache();
    const [u, c, s] = await Promise.all([
      fetchUniverses({ force }),
      fetchCoverage(UNIVERSE_ID, { force }),
      fetchSectors(),
    ]);
    setUniverses(u.error ? null : (u.data ?? null));
    setCoverage(c.error ? null : (c.data ?? null));
    setSectors(s.error ? null : (s.data?.sectors ?? null));
    setDataErrors([u.error, c.error, s.error].filter((error): error is string => Boolean(error)));
    setDataLoading(false);
  }, []);

  const loadOperatorsTab = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);
    const r = await fetchOperandCatalogWithSignatures();
    setCatalog(r.error ? null : (r.data ?? null));
    setCatalogError(r.error ?? (r.data ? null : "—"));
    setCatalogLoading(false);
  }, []);

  useEffect(() => { void loadDataTab(); }, [loadDataTab]);

  useEffect(() => {
    if (tab === "operators" && !catalog && !catalogError && !catalogLoading) void loadOperatorsTab();
  }, [tab, catalog, catalogError, catalogLoading, loadOperatorsTab]);

  const activeLoading = tab === "data"
    ? dataLoading
    : tab === "operators" && (catalogLoading || (!catalog && !catalogError));
  const activeErrors = tab === "data" ? dataErrors : tab === "operators" && catalogError ? [catalogError] : [];
  const hasData = Boolean(universes?.universes.length || coverage || sectors !== null);
  const dataComplete = Boolean(universes?.universes.some((u) => u.id === UNIVERSE_ID) && coverage?.universe_id === UNIVERSE_ID && sectors !== null);
  const incomplete = tab === "data" && !dataComplete;
  const fetchState = activeLoading ? text("读取中", "Loading")
    : activeErrors.length && (tab !== "data" || !hasData) ? text("读取失败", "Unavailable")
    : activeErrors.length || incomplete ? text("数据不完整", "Partial")
    : text("已读取", "Loaded");
  const staticTab = tab === "backtest" || tab === "evidence";
  const sourceLabel = staticTab ? text("静态定义", "Static definitions") : fetchState;
  const tone = staticTab || activeLoading ? "default" : activeErrors.length || incomplete ? "warning" : "positive";

  return (
    <TmScreen className="h-auto min-h-full">
      <WorkbenchHeader
        eyebrow={zh ? "参考" : "Reference"}
        title={t(locale, "methodology.title")}
        subtitle={zh ? "查数据来源、表达式能用的算子，以及回测指标怎么计算。" : "Look up data sources, callable operators, and how backtest metrics are calculated."}
        statuses={[{ label: zh ? "当前内容" : "Current content", value: sourceLabel[locale], tone }]}
      />
      <TmSubbar>
        {TABS.map((key) => (
          <TmChip key={key} on={tab === key} onClick={() => setTab(key)}>
            {t(locale, `methodology.tab.${key}`)}
          </TmChip>
        ))}
        <TmSubbarSpacer />
        {!staticTab && (activeLoading || activeErrors.length > 0 || incomplete) && (
          <TmStatusPill tone={activeErrors.length ? "err" : "warn"}>{fetchState[locale]}</TmStatusPill>
        )}
        {!staticTab && (
          <TmButton variant="ghost" size="xs" onClick={() => tab === "data" ? loadDataTab(true) : loadOperatorsTab()} disabled={activeLoading}>
            {activeLoading ? t(locale, "methodology.retrying") : activeErrors.length ? t(locale, "methodology.retry") : zh ? "刷新" : "Refresh"}
          </TmButton>
        )}
      </TmSubbar>

      {activeErrors.length > 0 && (
        <section>
        <TmStatePane
          state={tab === "data" && hasData ? "partial" : "error"}
          title={fetchState[locale]}
          description={zh ? "部分接口暂时不可用，可点击上方重试；字段与回测定义仍可查阅。" : "Some requests are unavailable. Retry above; field and backtest definitions remain accessible."}
          className="[overflow-wrap:anywhere]"
        />
        <details className="border-b border-tm-rule px-4 py-2 text-xs text-tm-muted">
          <summary className="cursor-pointer">{zh ? "技术详情" : "Technical details"}</summary>
          <ul className="mt-2 space-y-1 font-tm-mono [overflow-wrap:anywhere]">{[...new Set(activeErrors)].map(error=><li key={error}>{error}</li>)}</ul>
        </details>
        </section>
      )}
      {tab === "data" && <DataTab universes={universes} coverage={coverage} sectors={sectors} loading={dataLoading} />}
      {tab === "operators" && (catalog
        ? <OperatorsTab catalog={catalog} />
        : activeLoading && <TmStatePane state="loading" title={zh ? "正在读取算子目录" : "Loading operator catalog"} />)}
      {tab === "backtest" && <BacktestTab />}
      {tab === "evidence" && <EvidenceTab />}
    </TmScreen>
  );
}

const REPO_DOC = "https://github.com/zzzhhn/alpha-agent/blob/main/docs/research/";

/** P0 trading-methodology status. Static by design: it changes only when the audit is revised. */
function EvidenceTab() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const rows: readonly (readonly [string, ReactNode])[] = [
    [zh ? "当前结论" : "Current verdict", <span key="v" className="font-semibold text-tm-warn">Evidence insufficient</span>],
    [zh ? "含义" : "Meaning", zh ? "目前不能验证成本后赚钱能力，也不能凭短期亏损判定信号无效。晋升策略、扩大风险预算和盈利宣传均为 No-go。" : "Cost-adjusted profitability cannot be verified yet, and short-term losses do not prove the signal useless. Promoting the strategy, raising risk or claiming profits is No-go."],
    [zh ? "冻结协议" : "Frozen protocol", "quant-p0-v1.0.0-20261111"],
    [zh ? "前瞻窗口" : "Forward window", zh ? "2026-11-12 → 2027-11-12，至少 252 个可比交易日；到期前不提前挑窗口、不延长。" : "2026-11-12 → 2027-11-12, at least 252 comparable sessions; no early window picking or extension."],
    [zh ? "对照组" : "Controls", zh ? "SPY、现金、eligible 等权月度、12–1 动量 Top50 月度；全部含买卖双边成本。" : "SPY, cash, eligible equal-weight monthly and 12–1 momentum Top-50 monthly; all with two-sided costs."],
    [zh ? "主要已知问题" : "Known issues", zh ? "线上因子信号读 2026-10-30 的冻结面板；快照未记录价格下载时间；成交价与当前价格表因复权不一致；可执行看板首次读数为多头双边成本后 −4.89%，同期 SPY +1.52%（20 个区间，只作描述）。" : "The live factor signal reads a panel frozen at 2026-10-30; snapshots do not record price download time; fills differ from the revised price table; the first executable scoreboard read is −4.89% net long vs SPY +1.52% (20 intervals, descriptive only)."],
  ];
  return (
    <TmPane title={zh ? "交易方法论证据（P0）" : "Trading methodology evidence (P0)"} meta={zh ? "审计 2026-11-11" : "Audit 2026-11-11"}>
      <dl className="grid grid-cols-[minmax(7rem,auto)_minmax(0,1fr)] gap-x-6 gap-y-3 px-4 py-4 text-sm leading-6">
        {rows.map(([label, value]) => <div key={String(label)} className="contents"><dt className="text-tm-muted">{label}</dt><dd className="text-tm-fg-2 [overflow-wrap:anywhere]">{value}</dd></div>)}
      </dl>
      <div className="flex flex-wrap gap-2 border-t border-tm-rule px-4 py-3">
        <TmLinkButton href={`${REPO_DOC}2026-11-11-quant-p0-evidence-audit.md`} variant="secondary" size="sm" target="_blank" rel="noreferrer">{zh ? "证据审计" : "Evidence audit"}</TmLinkButton>
        <TmLinkButton href={`${REPO_DOC}2026-11-11-quant-p0-baseline-protocol.md`} variant="secondary" size="sm" target="_blank" rel="noreferrer">{zh ? "冻结协议" : "Frozen protocol"}</TmLinkButton>
      </div>
    </TmPane>
  );
}

function DataTab({
  universes, coverage, sectors, loading,
}: {
  readonly universes: UniverseListResponse | null;
  readonly coverage: CoverageResponse | null;
  readonly sectors: readonly string[] | null;
  readonly loading: boolean;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const universe = universes?.universes.find((u) => u.id === UNIVERSE_ID);
  const measured = coverage?.universe_id === UNIVERSE_ID ? coverage : null;
  const start = measured?.start_date ?? universe?.start_date;
  const end = measured?.end_date ?? universe?.end_date;
  const rows: CatalogRow[] = PANEL_SCHEMA.map((field) => ({
    id: field.name,
    title: field.name,
    group: field.group,
    search: [field.type, field.source, SCHEMA_PATTERNS[field.coverage][locale]],
    detail: [
      { label: zh ? "类型" : "Type", value: field.type, code: true },
      { label: zh ? "来源或推导" : "Source or derivation", value: field.source, code: true },
      { label: zh ? "数据形态" : "Data pattern", value: SCHEMA_PATTERNS[field.coverage][locale] },
    ],
    code: true,
  }));

  return (
    <>
      <TmPane title="PANEL.OVERVIEW" meta={UNIVERSE_ID}>
        <TmKpiGrid>
          <TmKpi label={t(locale, "methodology.data.tickers")} value={universe?.ticker_count ?? measured?.n_tickers ?? "—"} />
          <TmKpi label={t(locale, "methodology.data.days")} value={measured?.n_days ?? universe?.n_days ?? "—"} sub={start && end ? `${start} → ${end}` : undefined} />
          <TmKpi label={zh ? "收盘价实测覆盖率" : "Measured close coverage"} value={measured ? `${measured.ohlcv_coverage_pct.toFixed(2)}%` : "—"} sub={zh ? "非空收盘价单元格占比" : "Share of non-null close cells"} />
          <TmKpi label={t(locale, "methodology.data.benchmark")} value={universe?.benchmark ?? "—"} sub={universe?.currency} />
        </TmKpiGrid>
        {loading && <p role="status" className={INTRO_CLASS}>{zh ? "正在读取面板快照。下方字段定义不依赖这次请求。" : "Loading the panel snapshot. Field definitions below are available without it."}</p>}
      </TmPane>

      <Catalog
        title={text("面板字段", "Panel fields")}
        intro={text("字段名可用于核对表达式输入；这里列的是静态结构，不是实测覆盖率。", "Use the field names to check expression inputs. This is the static schema, not measured coverage.")}
        searchLabel={text("搜索字段名、类型或来源", "Search fields, types, or sources")}
        groupLabel={text("字段分组", "Field group")}
        allGroups={text("全部字段分组", "All field groups")}
        groups={SCHEMA_GROUPS}
        rows={rows}
      />

        <TmPane title="DATA.PIPELINE">
          <ol className="divide-y divide-tm-rule">
            {PIPELINE.map((stage, index) => (
              <li key={stage.source} className="grid min-w-0 grid-cols-[2rem_minmax(0,1fr)] gap-2 px-3 py-2 text-xs leading-relaxed">
                <span className="font-tm-mono tabular-nums text-tm-accent">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong className="font-semibold text-tm-fg">{stage.label[locale]}</strong>
                  <p className="text-tm-fg-2">{stage.description[locale]}</p>
                  <details className="mt-1">
                    <summary className="w-fit cursor-pointer text-tm-accent">{zh ? "来源" : "Source"}</summary>
                    <code className="block font-tm-mono text-tm-muted [overflow-wrap:anywhere]">{stage.source}</code>
                  </details>
                </div>
              </li>
            ))}
          </ol>
        </TmPane>
      <TmCols2>
          <TmPane title="BIAS.GUARDS">
            <ul className="divide-y divide-tm-rule">
              {(["survivorship", "lookahead"] as const).map((bias) => (
                <li key={bias} className="px-3 py-2 text-xs leading-relaxed">
                  <strong className="font-semibold text-tm-fg">{t(locale, `methodology.bias.${bias}.label`)}</strong>
                  <p className="text-tm-fg-2">{bias === "survivorship"
                    ? (zh ? "按每个历史交易日的指数成员筛选，不用今天的成分股回推历史。" : "Use the membership of each historical session rather than projecting today's constituents back in time.")
                    : (zh ? "财务数据按披露日而不是财季结束日对齐。首次披露前保留为缺值。" : "Align financials by disclosure date, not quarter-end. Values before the first disclosure remain missing.")}</p>
                  <code className="font-tm-mono text-tm-muted">{bias === "survivorship" ? "is_member (T,N)" : "RDQ ≤ t"}</code>
                </li>
              ))}
            </ul>
          </TmPane>
          <TmPane title="AVAILABLE.SECTORS" meta={sectors === null ? "—" : sectors.length}>
            {sectors && sectors.length > 0 ? (
              <ul className="flex flex-wrap gap-1.5 px-3 py-2">
                {sectors.map((sector) => <li key={sector} className="border border-tm-rule bg-tm-bg-2 px-2 py-px font-tm-mono text-xs text-tm-fg-2 [overflow-wrap:anywhere]">{sectorLabel(sector, locale)}</li>)}
              </ul>
            ) : <p className={INTRO_CLASS}>{loading ? t(locale, "common.loading") : sectors === null ? (zh ? "未读取到板块数据。" : "Sector data is unavailable.") : (zh ? "面板没有板块值。" : "The panel contains no sector values.")}</p>}
          </TmPane>
      </TmCols2>
    </>
  );
}

function OperatorsTab({ catalog }: { readonly catalog: OperandCatalogResponse }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const operators: readonly OperatorWithSignature[] = catalog.operators;
  const implemented = operators.filter((operator) => operator.implemented);
  const category = (operator: OperatorWithSignature) => operator.category || "uncategorized";
  const groups = Object.fromEntries(Array.from(new Set(implemented.map(category))).sort().map((key) => [key, OPERATOR_GROUPS[key] ?? text(key, key)]));
  const tiers = Array.from(new Set(implemented.map((operator) => operator.tier ?? "T1"))).sort();
  const rows: CatalogRow[] = implemented.map((operator) => {
    const description = zh ? (operator.description_zh || operator.description_en) : (operator.description_en || operator.description_zh);
    return {
      id: operator.name,
      title: operator.signature || operator.name,
      code: true,
      group: category(operator),
      tier: operator.tier ?? "T1",
      search: [operator.description_zh ?? "", operator.description_en ?? ""],
      detail: [
        ...(description ? [{ label: zh ? "用途" : "What it does", value: description }] : []),
        ...(operator.example ? [{ label: zh ? "示例" : "Example", value: operator.example, code: true }] : []),
        {
          label: zh ? "实现片段" : "Implementation excerpt",
          value: operator.source_snippet || (zh ? "本次目录未返回源码片段。" : "This catalog response did not include a source excerpt."),
          block: Boolean(operator.source_snippet),
        },
      ],
    };
  });

  return (
    <Catalog
      title={text("运算符目录", "Operator catalog")}
      intro={text(
        `已登记 ${operators.length} 个算子，其中 ${implemented.length} 个可调用。展开查看用途、示例和可用的源码片段。`,
        `${implemented.length} of ${operators.length} registered operators are callable. Expand a row for usage, examples, and any available source excerpt.`,
      )}
      searchLabel={text("搜索算子名、签名或用途", "Search operators, signatures, or descriptions")}
      groupLabel={text("算子类别", "Operator category")}
      allGroups={text("全部算子类别", "All operator categories")}
      groups={groups}
      rows={rows}
      tiers={tiers}
    />
  );
}

const PORTFOLIO = [
  { label: text("按因子排名建仓", "Rank and weight"), description: text("每天按 factor[t] 对股票排序。排名前 top_pct 的标的等权做多，后 bottom_pct 的标的等权做空。", "Rank securities by factor[t] each day. Equal-weight the top top_pct as longs and the bottom bottom_pct as shorts.") },
  { label: text("持仓与次日收益对齐", "Align weights and returns"), description: text("用前一日确定的权重计算次日收益：sum(weights[t-1] × fwd_returns[t-1])。", "Pair the prior day's weights with the next day's return: sum(weights[t-1] × fwd_returns[t-1]).") },
  { label: text("按换手扣交易成本", "Deduct trading costs"), description: text("按两日之间的权重变动扣减日收益：bps × L1(weights[t] − weights[t-1]) / 10000。", "Deduct costs from daily returns based on the change in weights: bps × L1(weights[t] − weights[t-1]) / 10000.") },
  { label: text("滚动观察稳定性", "Check stability over time"), description: text("Walk-forward 模式在静态切分之外，按 wf_window_days 滚动计算各窗口指标。", "Walk-forward mode adds rolling metrics over wf_window_days windows alongside the static split.") },
  { label: text("各页面的样本切分", "Sample split by page"), description: text("回测与因子页：训练 80% / 测试 20%（后端默认）。报告页：训练 70% / 测试 30%（固定）。演化页因子验证：前 60% 只用于搜索，后 40% 分成 3 个连续折、每折前留 5 个交易日空档，各折独立计算样本外 Sharpe 与 IC。三处数字不能直接互比。", "Backtest and Alpha: 80% train / 20% test (backend default). Report: 70% / 30% (fixed). Evolution factor validation: the first 60% is search-only; the last 40% is split into three contiguous folds with a five-session embargo, each scored out of sample. The three are not directly comparable.") },
] as const;

function BacktestTab() {
  const { locale } = useLocale();
  const rows: CatalogRow[] = METRIC_ROWS.map((row) => {
    const key = `methodology.backtest.${row.keyBase}` as Parameters<typeof t>[1];
    return {
      id: row.keyBase,
      title: t(locale, key),
      group: row.category,
      search: [t("zh", key), t("en", key), row.formula, row.ref],
      detail: [
        { label: t(locale, "methodology.backtest.colFormula"), value: row.formula, code: true },
        { label: t(locale, "methodology.backtest.colRef"), value: row.ref, code: true },
      ],
    };
  });

  return (
    <>
      <Catalog
        title={text("回测指标公式", "Backtest formulas")}
        intro={text("回测按因子排名构建等权多空组合，计算次日收益，再扣交易成本。展开指标可核对公式和实现位置。", "The backtest ranks securities, builds an equal-weight long/short portfolio, and deducts trading costs from next-day returns. Expand a metric for its formula and source.")}
        searchLabel={text("搜索指标名、公式或代码位置", "Search metrics, formulas, or source references")}
        groupLabel={text("指标类别", "Metric category")}
        allGroups={text("全部指标类别", "All metric categories")}
        groups={METRIC_GROUPS}
        rows={rows}
      />
      <TmPane title={t(locale, "methodology.backtest.portfolioTitle")}>
        <ol className="grid min-w-0 gap-px bg-tm-rule md:grid-cols-2">
          {PORTFOLIO.map((rule) => (
            <li key={rule.label.en} className="min-w-0 bg-tm-bg px-3 py-2 text-xs leading-relaxed [overflow-wrap:anywhere]">
              <strong className="font-semibold text-tm-fg">{rule.label[locale]}</strong>
              <p className="text-tm-fg-2">{rule.description[locale]}</p>
            </li>
          ))}
        </ol>
      </TmPane>
    </>
  );
}

const INTRO_CLASS = "px-3 py-2 text-xs leading-relaxed text-tm-fg-2";

interface CatalogRow {
  readonly id: string;
  readonly title: string;
  readonly group: string;
  readonly tier?: string;
  readonly code?: boolean;
  readonly search: readonly string[];
  readonly detail: readonly { readonly label: string; readonly value: ReactNode; readonly code?: boolean; readonly block?: boolean }[];
}

function Catalog({
  title, intro, searchLabel, groupLabel, allGroups, groups, rows, tiers,
}: {
  readonly title: LocalText;
  readonly intro: LocalText;
  readonly searchLabel: LocalText;
  readonly groupLabel: LocalText;
  readonly allGroups: LocalText;
  readonly groups: Readonly<Record<string, LocalText>>;
  readonly rows: readonly CatalogRow[];
  readonly tiers?: readonly string[];
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const disclosureGroup = useId();
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("all");
  const [tier, setTier] = useState("all");
  const [page, setPage] = useState(1);
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const filtered = rows.filter((row) => {
    if (group !== "all" && row.group !== group) return false;
    if (tier !== "all" && row.tier !== tier) return false;
    const labels = groups[row.group];
    const haystack = [row.id, row.title, row.group, labels?.zh, labels?.en, row.tier, ...row.search].join(" ").toLowerCase();
    return tokens.every((token) => haystack.includes(token));
  });
  const visiblePage = Math.min(page, Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
  const start = (visiblePage - 1) * PAGE_SIZE;

  return (
    <TmPane title={<h2>{title[locale]}</h2>}>
      <p className={INTRO_CLASS}>{intro[locale]}</p>
      <div className="flex min-w-0 flex-wrap items-center gap-2 border-y border-tm-rule bg-tm-bg-2 px-3 py-2">
        <TmInput
          type="search"
          fieldSize="sm"
          aria-label={searchLabel[locale]}
          placeholder={searchLabel[locale]}
          value={query}
          onChange={(value) => { setQuery(value); setPage(1); }}
          className="w-full min-w-0 sm:w-72"
        />
        <TmSelectMenu
          value={group}
          ariaLabel={groupLabel[locale]}
          options={[{ value: "all", label: allGroups[locale] }, ...Object.entries(groups).map(([value, label]) => ({ value, label: label[locale] }))]}
          onChange={(value) => { setGroup(value); setPage(1); }}
        />
        {tiers && (
          <TmSelectMenu
            value={tier}
            ariaLabel={zh ? "算子层级" : "Operator tier"}
            options={[{ value: "all", label: zh ? "全部层级" : "All tiers" }, ...tiers.map((value) => ({ value, label: value }))]}
            onChange={(value) => { setTier(value); setPage(1); }}
          />
        )}
      </div>

      {filtered.length > 0 ? (
        <ul key={JSON.stringify([visiblePage, query, group, tier])} className="min-w-0 divide-y divide-tm-rule">
          {filtered.slice(start, start + PAGE_SIZE).map((row) => (
            <li key={row.id} className="min-w-0">
              <details name={disclosureGroup} className="group min-w-0">
                <summary className="grid min-h-8 cursor-pointer list-none grid-cols-[0.75rem_minmax(0,1fr)] items-center gap-x-2 gap-y-1 px-3 py-1.5 text-xs hover:bg-tm-bg-2 focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-tm-accent group-open:bg-tm-bg-2 sm:grid-cols-[0.75rem_minmax(0,1fr)_auto] [&::-webkit-details-marker]:hidden">
                  <span aria-hidden="true" className="text-tm-accent"><span className="group-open:hidden">+</span><span className="hidden group-open:inline">−</span></span>
                  <span className={`min-w-0 font-semibold text-tm-fg [overflow-wrap:anywhere] ${row.code ? "font-tm-mono" : ""}`}>{row.title}</span>
                  <span className="col-start-2 min-w-0 text-tm-muted [overflow-wrap:anywhere] sm:col-start-3 sm:text-right">
                    {[groups[row.group]?.[locale] ?? row.group, row.tier].filter(Boolean).join(" · ")}
                  </span>
                </summary>
                <dl className="grid min-w-0 gap-x-4 gap-y-1 border-t border-tm-rule bg-tm-bg-2 py-2 pl-8 pr-3 text-xs leading-relaxed sm:grid-cols-[8rem_minmax(0,1fr)]">
                  {row.detail.map((item) => (
                    <div key={item.label} className="contents">
                      <dt className="font-semibold text-tm-muted">{item.label}</dt>
                      <dd className="min-w-0 text-tm-fg-2 [overflow-wrap:anywhere]">
                        {item.block
                          ? <pre className="m-0 whitespace-pre-wrap font-tm-mono">{item.value}</pre>
                          : item.code ? <code className="font-tm-mono">{item.value}</code> : item.value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className={INTRO_CLASS} role="status">{rows.length
          ? (zh ? "没有匹配项。试试其他关键词或清除筛选。" : "No matches. Try another search or clear the filters.")
          : (zh ? "目录没有返回条目。" : "The catalog returned no entries.")}</p>
      )}
      <TmPagination
        page={visiblePage}
        pageSize={PAGE_SIZE}
        pageSizeOptions={[PAGE_SIZE]}
        totalItems={filtered.length}
        onPageChange={setPage}
        onPageSizeChange={() => {}}
        labels={{
          navigation: zh ? `${title.zh}分页` : `${title.en} pagination`,
          previous: "‹",
          previousAriaLabel: zh ? "上一页" : "Previous page",
          next: "›",
          nextAriaLabel: zh ? "下一页" : "Next page",
          page: (current, total) => `${current} / ${total}`,
          pageSize: zh ? "每页" : "Rows per page",
          total: (count) => zh
            ? `显示 ${count ? start + 1 : 0}–${Math.min(start + PAGE_SIZE, count)} · 匹配 ${count} / ${rows.length} 条`
            : `Showing ${count ? start + 1 : 0}–${Math.min(start + PAGE_SIZE, count)} · ${count} of ${rows.length} matched`,
        }}
      />
    </TmPane>
  );
}
