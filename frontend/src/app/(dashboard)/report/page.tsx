"use client";

/**
 * Report page — workstation port (Stage 3 · 8/9).
 *
 * Tear-sheet generator. Two slots: "primary" (the headline factor) and
 * "compare" (an optional second factor for side-by-side overlay).
 * Both slots run through fetchAll() which spawns runFactorBacktest +
 * signalToday + signalExposure in parallel.
 *
 * Layout: TmSubbar (factor name + universe + status pills + print
 * button) → REPORT.PICKER pane (config chips + example chips + zoo
 * chips + custom-input + compare chips) → COMPARE.OVERLAY pane (when
 * both slots filled) → primary tearsheet sequence (REPORT.COVER →
 * BACKTEST.KPI → EQUITY.UNDERWATER (FactorPnLChart wrapped) →
 * DRAWDOWN → MONTHLY → SIGNAL.TODAY → EXPOSURE) → compare tearsheet.
 *
 * Behavior preserved byte-for-byte: REPORT_PREFILL_KEY handoff from
 * /factors, ReportConfig propagation, fetchAll triple-fetch, print
 * via window.print(), example loadExample auto-runs with locale-
 * appropriate intuition, zoo-entry handoff, compare slot management.
 *
 * NOTE: this is the LAST page using legacy BacktestKpiStrip /
 * DrawdownChart / MonthlyReturnsHeatmap / TopBottomTable /
 * ExposureChart / CompareEquityChart imports. After this port lands,
 * the legacy components are dead code and can be removed in S5 polish.
 */

import { useCallback, useEffect, useState, type ChangeEvent } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { extractOps } from "@/lib/factor-spec";
import { t } from "@/lib/i18n";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
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
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { TmBacktestKpiStrip } from "@/components/backtest/TmBacktestKpiStrip";
import { TmDrawdownChart } from "@/components/backtest/TmDrawdownChart";
import { TmMonthlyReturnsHeatmap } from "@/components/backtest/TmMonthlyReturnsHeatmap";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { TmCompareEquityChart } from "@/components/charts/TmCompareEquityChart";
import { TmTopBottomTable } from "@/components/signal/TmTopBottomTable";
import { TmExposureChart } from "@/components/signal/TmExposureChart";
import { listZoo, type ZooEntry } from "@/lib/factor-zoo";
import {
  runFactorBacktest,
  signalToday,
  signalExposure,
} from "@/lib/api";
import type {
  FactorBacktestResponse,
  SignalSpec,
  SignalTodayResponse,
  ExposureResponse,
} from "@/lib/types";

interface FactorReport {
  readonly name: string;
  readonly expression: string;
  readonly intuition: string;
  readonly backtest: FactorBacktestResponse;
  readonly today: SignalTodayResponse;
  readonly exposure: ExposureResponse;
}

const REPORT_PREFILL_KEY = "alphacore.report.prefill.v1";

export interface ReportConfig {
  readonly direction: "long_short" | "long_only" | "short_only";
  readonly neutralize: "none" | "sector";
  readonly benchmarkTicker: "SPY" | "RSP";
  readonly transactionCostBps: number;
}

const DEFAULT_REPORT_CONFIG: ReportConfig = {
  direction: "long_short",
  neutralize: "none",
  benchmarkTicker: "SPY",
  transactionCostBps: 5,
};

// Backend FactorSpec.hypothesis is bounded to 200 chars (Pydantic
// max_length=200). UI display strings (intuitionZh, hypothesisZh on
// some v3 examples, free-form user input) can blow past that.
// Truncating at the boundary so no caller can break the contract.
const MAX_HYPOTHESIS_CHARS = 200;
function clipHypothesis(s: string): string {
  if (s.length <= MAX_HYPOTHESIS_CHARS) return s;
  // Reserve 1 char for the ellipsis so backend gets exactly 200.
  return s.slice(0, MAX_HYPOTHESIS_CHARS - 1) + "…";
}

async function fetchAll(
  name: string,
  expression: string,
  hypothesis: string,
  cfg: ReportConfig,
) {
  const spec: SignalSpec = {
    name: name || "factor",
    hypothesis: clipHypothesis(hypothesis || expression),
    expression,
    operators_used: [...extractOps(expression)],
    lookback: 12,
    universe: "SP500",
    justification: "tear sheet generation",
  };
  return Promise.all([
    runFactorBacktest({
      spec,
      train_ratio: 0.7,
      direction: cfg.direction,
      top_pct: 0.30,
      bottom_pct: 0.30,
      transaction_cost_bps: cfg.transactionCostBps,
      neutralize: cfg.neutralize,
      benchmark_ticker: cfg.benchmarkTicker,
    }),
    signalToday(spec, 10, cfg.neutralize),
    signalExposure(spec, 10, cfg.neutralize),
  ]);
}

export default function ReportPage() {
  const { locale } = useLocale();
  const [factorName, setFactorName] = useState<string>("");
  const [expr, setExpr] = useState<string>("");
  const [intuition, setIntuition] = useState<string>("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [primary, setPrimary] = useState<FactorReport | null>(null);
  const [compare, setCompare] = useState<FactorReport | null>(null);
  const [zoo, setZoo] = useState<readonly ZooEntry[]>([]);
  const [config, setConfig] = useState<ReportConfig>(DEFAULT_REPORT_CONFIG);

  useEffect(() => {
    setZoo(listZoo());
  }, []);

  // generate accepts hypothesis (short, ≤200 chars, sent to backend)
  // and an optional intuitionForCover (display-only, can be longer).
  // The split avoids the bug where intuitionZh (~220 chars on v3 picks)
  // leaked into the backend hypothesis field and triggered HTTP 422.
  const generate = useCallback(
    async (
      name: string,
      expression: string,
      hypothesis: string,
      slot: "primary" | "compare",
      intuitionForCover?: string,
    ) => {
      setRunning(true);
      setError(null);
      const [bt, td, ex] = await fetchAll(name, expression, hypothesis, config);
      if (
        bt.error || td.error || ex.error ||
        !bt.data || !td.data || !ex.data
      ) {
        setError(bt.error ?? td.error ?? ex.error ?? "unknown error");
        setRunning(false);
        return;
      }
      const built: FactorReport = {
        name,
        expression,
        intuition: intuitionForCover ?? hypothesis,
        backtest: bt.data,
        today: td.data,
        exposure: ex.data,
      };
      if (slot === "primary") {
        setPrimary(built);
        setCompare(null);
      } else {
        setCompare(built);
      }
      setRunning(false);
    },
    [config],
  );

  // P6.D — read /factors zoo handoff (if any) and auto-generate.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(REPORT_PREFILL_KEY);
      if (!raw) return;
      window.sessionStorage.removeItem(REPORT_PREFILL_KEY);
      const e = JSON.parse(raw) as ZooEntry;
      if (!e?.expression) return;
      setFactorName(e.name);
      setExpr(e.expression);
      setIntuition(e.intuition ?? "");
      void generate(
        e.name,
        e.expression,
        e.hypothesis ?? "",
        "primary",
        e.intuition ?? e.hypothesis ?? "",
      );
    } catch {
      /* malformed handoff — ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function loadExample(example: FactorExample) {
    setFactorName(example.name);
    setExpr(example.expression);
    const intu =
      locale === "zh" ? example.intuitionZh : example.intuitionEn;
    setIntuition(intu);
    // v3: pull example's proven config too so the report matches the
    // verdict the example was discovered under.
    setConfig((c) => ({
      direction: example.direction ?? c.direction,
      neutralize: example.neutralize ?? c.neutralize,
      benchmarkTicker: example.benchmarkTicker ?? c.benchmarkTicker,
      transactionCostBps: example.transactionCostBps ?? c.transactionCostBps,
    }));
    void generate(
      example.name,
      example.expression,
      locale === "zh" ? example.hypothesisZh : example.hypothesisEn,
      "primary",
      intu, // long display text on the cover; backend hypothesis stays short
    );
  }

  function loadZooEntry(e: ZooEntry, slot: "primary" | "compare") {
    if (slot === "primary") {
      setFactorName(e.name);
      setExpr(e.expression);
      setIntuition(e.intuition ?? "");
    }
    void generate(
      e.name,
      e.expression,
      e.hypothesis ?? "",
      slot,
      e.intuition ?? e.hypothesis ?? "",
    );
  }

  function runCustom() {
    if (!expr.trim()) return;
    // intuition is the long human-readable display field; do NOT pass
    // it as backend hypothesis (Pydantic 200-char cap). For custom user
    // input we synthesize a short hypothesis but pass the user's full
    // intuition through as the cover-display field. clipHypothesis at
    // fetchAll guards anyway.
    const name = factorName.trim() || "user_factor";
    void generate(
      name,
      expr.trim(),
      `tearsheet for ${name}`,
      "primary",
      intuition,
    );
  }

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">REPORT</span>
        <TmSubbarSep />
        <TmSubbarKV
          label="FACTOR"
          value={primary?.name ?? factorName ?? "—"}
        />
        {primary && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="UNIVERSE"
              value={`${primary.today.universe_size}`}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label="SHARPE"
              value={primary.backtest.test_metrics.sharpe.toFixed(2)}
            />
          </>
        )}
        {compare && (
          <>
            <TmSubbarSep />
            <TmSubbarKV label="COMPARE" value={compare.name} />
          </>
        )}
        <TmSubbarSpacer />
        {primary?.backtest.overfit_flag && (
          <TmStatusPill tone="err">
            OVERFIT · OOS DECAY{" "}
            {((primary.backtest.oos_decay ?? 0) * 100).toFixed(0)}%
          </TmStatusPill>
        )}
        {primary && (
          <TmStatusPill
            tone={primary.backtest.survivorship_corrected ? "ok" : "warn"}
          >
            {primary.backtest.survivorship_corrected
              ? `SP500-AS-OF · ${primary.backtest.membership_as_of ?? "—"}`
              : "LEGACY"}
          </TmStatusPill>
        )}
        {running && <TmStatusPill tone="warn">RUNNING…</TmStatusPill>}
        {error && <TmStatusPill tone="err">ERROR</TmStatusPill>}
        {primary && (
          <TmButton
            variant="ghost"
            onClick={() => window.print()}
            className="-my-1 px-2"
          >
            {t(locale, "report.exportPdf")}
          </TmButton>
        )}
      </TmSubbar>

      <ReportPickerPane
        factorName={factorName}
        onFactorName={setFactorName}
        expr={expr}
        onExpr={setExpr}
        config={config}
        onConfig={setConfig}
        zoo={zoo}
        primary={primary}
        compare={compare}
        running={running}
        loadExample={loadExample}
        loadZooEntry={loadZooEntry}
        runCustom={runCustom}
        generate={generate}
        clearCompare={() => setCompare(null)}
      />

      {error && (
        <TmPane title="ERROR" meta="report generation failed">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {error}
          </p>
        </TmPane>
      )}

      {primary && compare && (
        <TmPane
          title="COMPARE.OVERLAY"
          meta={`${primary.name} vs ${compare.name} vs ${primary.backtest.benchmark_ticker}`}
        >
          <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
            {t(locale, "report.compare.subtitle")
              .replace("{a}", primary.name)
              .replace("{b}", compare.name)}
          </p>
          <TmCompareEquityChart
            factor1Name={primary.name}
            factor1={primary.backtest.equity_curve}
            factor2Name={compare.name}
            factor2={compare.backtest.equity_curve}
            benchmark={primary.backtest.benchmark_curve}
            benchmarkTicker={primary.backtest.benchmark_ticker}
          />
        </TmPane>
      )}

      {primary && (
        <article className="report-tearsheet flex flex-col">
          <ReportCoverPane
            r={primary}
            expr={primary.expression}
            factorName={primary.name}
            intuition={primary.intuition}
            config={config}
          />
          <TmBacktestKpiStrip result={primary.backtest} />
          <TmPane
            title="EQUITY.CURVE"
            meta={`${primary.backtest.equity_curve.length} sessions · vs ${primary.backtest.benchmark_ticker}`}
          >
            <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
              {t(locale, "backtest.equity.subtitle")}
            </p>
            <div className="px-2 pb-2 pt-2">
              <FactorPnLChart data={primary.backtest} height={260} />
            </div>
          </TmPane>
          <TmDrawdownChart equityCurve={primary.backtest.equity_curve} />
          {primary.backtest.monthly_returns &&
            primary.backtest.monthly_returns.length > 0 && (
              <TmMonthlyReturnsHeatmap
                data={primary.backtest.monthly_returns}
              />
            )}
          <TmTopBottomTable today={primary.today} loading={false} />
          <TmExposureChart
            data={primary.exposure}
            topN={10}
            loading={false}
          />
        </article>
      )}

      {compare && (
        <article className="report-tearsheet flex flex-col">
          <TmPane title="REPORT.COMPARE" meta="second factor tear sheet">
            <p className="px-3 py-2 font-tm-mono text-[10.5px] uppercase tracking-[0.06em] text-tm-info">
              {t(locale, "report.compare.secondLabel")}
            </p>
          </TmPane>
          <ReportCoverPane
            r={compare}
            expr={compare.expression}
            factorName={compare.name}
            intuition={compare.intuition}
            config={config}
          />
          <TmBacktestKpiStrip result={compare.backtest} />
          <TmDrawdownChart equityCurve={compare.backtest.equity_curve} />
          {compare.backtest.monthly_returns &&
            compare.backtest.monthly_returns.length > 0 && (
              <TmMonthlyReturnsHeatmap
                data={compare.backtest.monthly_returns}
              />
            )}
          <TmTopBottomTable today={compare.today} loading={false} />
          <TmExposureChart
            data={compare.exposure}
            topN={10}
            loading={false}
          />
        </article>
      )}

      {!primary && !running && (
        <TmPane title="USAGE" meta="hint">
          <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {t(locale, "report.subtitle")}
          </p>
        </TmPane>
      )}
    </TmScreen>
  );
}

/* ── REPORT.PICKER pane ───────────────────────────────────────────── */

function ReportPickerPane({
  factorName,
  onFactorName,
  expr,
  onExpr,
  config,
  onConfig,
  zoo,
  primary,
  compare,
  running,
  loadExample,
  loadZooEntry,
  runCustom,
  generate,
  clearCompare,
}: {
  readonly factorName: string;
  readonly onFactorName: (v: string) => void;
  readonly expr: string;
  readonly onExpr: (v: string) => void;
  readonly config: ReportConfig;
  readonly onConfig: (
    fn: ReportConfig | ((c: ReportConfig) => ReportConfig),
  ) => void;
  readonly zoo: readonly ZooEntry[];
  readonly primary: FactorReport | null;
  readonly compare: FactorReport | null;
  readonly running: boolean;
  readonly loadExample: (e: FactorExample) => void;
  readonly loadZooEntry: (e: ZooEntry, slot: "primary" | "compare") => void;
  readonly runCustom: () => void;
  readonly generate: (
    name: string,
    expression: string,
    hypothesis: string,
    slot: "primary" | "compare",
    intuitionForCover?: string,
  ) => void;
  readonly clearCompare: () => void;
}) {
  const { locale } = useLocale();

  return (
    <TmPane
      title="REPORT.PICKER"
      meta={`${FACTOR_EXAMPLES.length} EXAMPLES · ${zoo.length} ZOO · ${primary ? "GENERATED" : "EMPTY"}`}
    >
      <div className="flex flex-col gap-3 px-3 py-3">
        {/* Config chip rows: direction / neutralize / benchmark / cost */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ConfigChipGroup
            label="direction"
            options={["long_short", "long_only", "short_only"]}
            value={config.direction}
            onChange={(v) => onConfig((c) => ({ ...c, direction: v as ReportConfig["direction"] }))}
          />
          <ConfigChipGroup
            label={t(locale, "backtest.form.neutralize")}
            options={["none", "sector"]}
            value={config.neutralize}
            onChange={(v) => onConfig((c) => ({ ...c, neutralize: v as "none" | "sector" }))}
          />
          <ConfigChipGroup
            label={t(locale, "backtest.form.benchmark")}
            options={["SPY", "RSP"]}
            value={config.benchmarkTicker}
            onChange={(v) => onConfig((c) => ({ ...c, benchmarkTicker: v as "SPY" | "RSP" }))}
          />
          <div className="flex items-center gap-2">
            <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
              cost bps
            </span>
            <input
              type="number"
              min={0}
              max={50}
              step={1}
              value={config.transactionCostBps}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                onConfig((c) => ({
                  ...c,
                  transactionCostBps: Number(e.target.value) || 0,
                }))
              }
              className="h-6 w-14 border border-tm-rule bg-tm-bg-2 px-2 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg outline-none focus:border-tm-accent"
            />
          </div>
        </div>

        {/* From examples */}
        <div className="border-t border-tm-rule pt-2.5">
          <p className="mb-1.5 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
            {t(locale, "report.picker.fromExamples")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {FACTOR_EXAMPLES.map((example) => (
              <TmChip
                key={example.name}
                onClick={() => loadExample(example)}
                disabled={running}
              >
                {example.name}
              </TmChip>
            ))}
          </div>
        </div>

        {/* From zoo */}
        {zoo.length > 0 && (
          <div className="border-t border-tm-rule pt-2.5">
            <p className="mb-1.5 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "report.picker.fromZoo")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {zoo.slice(0, 12).map((z) => (
                <TmChip
                  key={z.id}
                  onClick={() => loadZooEntry(z, "primary")}
                  disabled={running}
                  title={z.expression}
                >
                  {z.name}
                </TmChip>
              ))}
            </div>
          </div>
        )}

        {/* Custom input */}
        <div className="flex flex-col gap-2 border-t border-tm-rule pt-2.5">
          <input
            type="text"
            value={factorName}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              onFactorName(e.target.value)
            }
            placeholder={t(locale, "report.picker.namePlaceholder")}
            className="h-8 w-full border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11.5px] text-tm-fg outline-none placeholder:text-tm-muted focus:border-tm-accent"
          />
          <textarea
            value={expr}
            onChange={(e) => onExpr(e.target.value)}
            placeholder={t(locale, "report.picker.exprPlaceholder")}
            rows={2}
            spellCheck={false}
            className="w-full resize-none border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg outline-none focus:border-tm-accent"
          />
          <div className="flex justify-end">
            <TmButton
              variant="primary"
              onClick={runCustom}
              disabled={running || expr.trim().length === 0}
            >
              {running
                ? t(locale, "report.picker.running")
                : t(locale, "report.picker.generate")}
            </TmButton>
          </div>
        </div>

        {/* Compare slot — appears once primary is set */}
        {primary && (
          <div className="border-t border-tm-rule pt-2.5">
            <p className="mb-1 font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
              {t(locale, "report.picker.compareTitle")}
            </p>
            <p className="mb-1.5 font-tm-mono text-[10.5px] text-tm-muted">
              {t(locale, "report.picker.compareSubtitle")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {FACTOR_EXAMPLES.filter(
                (e) => e.expression !== primary.expression,
              ).map((example) => (
                <TmChip
                  key={example.name}
                  onClick={() =>
                    generate(
                      example.name,
                      example.expression,
                      locale === "zh"
                        ? example.hypothesisZh
                        : example.hypothesisEn,
                      "compare",
                      locale === "zh"
                        ? example.intuitionZh
                        : example.intuitionEn,
                    )
                  }
                  disabled={running}
                >
                  + {example.name}
                </TmChip>
              ))}
              {zoo
                .filter((z) => z.expression !== primary.expression)
                .slice(0, 6)
                .map((z) => (
                  <TmChip
                    key={z.id}
                    onClick={() => loadZooEntry(z, "compare")}
                    disabled={running}
                  >
                    + {z.name}
                  </TmChip>
                ))}
              {compare && (
                <TmButton
                  variant="ghost"
                  onClick={clearCompare}
                  className="h-6 px-2 text-[10px]"
                >
                  {t(locale, "report.picker.compareClear")}
                </TmButton>
              )}
            </div>
          </div>
        )}
      </div>
    </TmPane>
  );
}

function ConfigChipGroup({
  label,
  options,
  value,
  onChange,
}: {
  readonly label: string;
  readonly options: readonly string[];
  readonly value: string;
  readonly onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </span>
      {options.map((o) => (
        <TmChip key={o} on={value === o} onClick={() => onChange(o)}>
          {o}
        </TmChip>
      ))}
    </div>
  );
}

/* ── REPORT.COVER pane (per slot) ─────────────────────────────────── */

function ReportCoverPane({
  r,
  expr,
  factorName,
  intuition,
  config,
}: {
  readonly r: FactorReport;
  readonly expr: string;
  readonly factorName: string;
  readonly intuition: string;
  readonly config: ReportConfig;
}) {
  const { locale } = useLocale();
  const eq = r.backtest.equity_curve;
  const startDate = eq[0]?.date ?? "—";
  const endDate = eq[eq.length - 1]?.date ?? "—";
  const totalRet =
    eq.length > 0 ? eq[eq.length - 1].value / eq[0].value - 1 : 0;
  const benchEq = r.backtest.benchmark_curve;
  const benchRet =
    benchEq.length > 0
      ? benchEq[benchEq.length - 1].value / benchEq[0].value - 1
      : 0;

  return (
    <TmPane
      title="REPORT.COVER"
      meta={`${factorName || r.backtest.factor_name} · ${r.today.universe_size} tickers`}
    >
      <div className="border-b border-tm-rule px-3 py-2.5">
        <h2 className="font-tm-mono text-[14px] font-semibold uppercase tracking-[0.04em] text-tm-accent">
          {factorName || r.backtest.factor_name}
        </h2>
        <code className="mt-1 block break-all font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
          {expr}
        </code>
      </div>

      <TmKpiGrid>
        <TmKpi
          label="UNIVERSE"
          value={r.today.universe_size.toString()}
          sub="SP500 panel"
        />
        <TmKpi
          label="WINDOW"
          value={`${eq.length}d`}
          sub={`${startDate} → ${endDate}`}
        />
        <TmKpi
          label="BENCHMARK"
          value={r.backtest.benchmark_ticker}
          sub={`${(benchRet * 100).toFixed(1)}% over slice`}
        />
        <TmKpi
          label="DIRECTION"
          value={config.direction}
          sub={
            config.neutralize === "sector"
              ? "sector-neutral"
              : "no neutralize"
          }
        />
        <TmKpi
          label="COST"
          value={`${config.transactionCostBps}bps`}
          sub="round-trip"
        />
        <TmKpi
          label="TOTAL RET"
          value={`${(totalRet * 100).toFixed(1)}%`}
          tone={totalRet > benchRet ? "pos" : "neg"}
          sub={`vs ${(benchRet * 100).toFixed(1)}% bench`}
        />
      </TmKpiGrid>

      {intuition && (
        <p className="border-t border-tm-rule px-3 py-2.5 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
          {intuition}
        </p>
      )}

      <p className="border-t border-tm-rule bg-tm-bg-2 px-3 py-1 font-tm-mono text-[9.5px] uppercase tracking-[0.06em] text-tm-muted">
        {t(locale, "report.cover.generated")}:{" "}
        {new Date().toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}
      </p>
    </TmPane>
  );
}
