"use client";

/**
 * Alpha page — workstation port (Stage 3 · 9/9, FINAL).
 *
 * Natural-language → FactorSpec translation pipeline. User types a
 * hypothesis in plain English / Chinese, LLM returns a structured
 * spec (name / expression / operators / lookback / justification),
 * smoke-test fires synchronously to surface IC + runtime sanity, then
 * an inline quick-backtest can run via direction toggle.
 *
 * Layout: TmSubbar (universe + direction + status pills + run button +
 *   BYOK shortcut) → HYPOTHESIS.INPUT pane (textarea + tips) →
 *   FACTOR.EXAMPLES pane (10 unique deduped picks as cards with full
 *   intuition, hypothesis, ops; click loads into textarea) →
 *   TRANSLATE.RESULT pane (TmCols2: SPEC dl on left, SMOKE.PROBE
 *   KPIs on right) → ASTDrawer (preserved, click to view tree) →
 *   BACKTEST.QUICK pane (direction chips + 6 KPIs + FactorPnLChart) →
 *   HYPOTHESIS.HISTORY pane (favorites + recent, was right-rail
 *   sidebar in legacy; merged into bottom of flow).
 *
 * Behavior preserved byte-for-byte: translateHypothesis flow, smoke
 * sanity check, addToHistory + favorite/remove, ASTDrawer, ZooSave,
 * jumpToBacktest sessionStorage handoff, BYOK error CTA → /settings.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
import { extractOps } from "@/lib/factor-spec";
import { PROVIDER_PRESETS, type LLMProvider } from "@/lib/byok";
import { getByok, type ByokGetResponse } from "@/lib/api/user";
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
import { TmSelect } from "@/components/tm/TmField";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { ZooSaveButton } from "@/components/zoo/ZooSaveButton";
import {
  FACTOR_EXAMPLES,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
import { ASTDrawer } from "@/components/alpha/ASTDrawer";
import {
  addToHistory,
  getFavorites,
  getHistory,
  getRecent,
  removeFromHistory,
  toggleFavorite,
} from "@/lib/hypothesis-history";
import type {
  BacktestDirection,
  FactorBacktestResponse,
  FactorUniverse,
  HypothesisHistoryEntry,
  HypothesisTranslateRequest,
  HypothesisTranslateResponse,
} from "@/lib/types";

const UNIVERSE_OPTIONS: readonly { value: FactorUniverse; label: string }[] = [
  { value: "CSI300", label: "CSI300" },
  { value: "CSI500", label: "CSI500" },
  { value: "SP500", label: "S&P500" },
  { value: "custom", label: "Custom" },
];

const DIRECTION_HELP_KEY: Record<BacktestDirection, TranslationKey> = {
  long_short: "alpha.backtest.dirHelpLongShort",
  long_only: "alpha.backtest.dirHelpLongOnly",
  short_only: "alpha.backtest.dirHelpShortOnly",
};

export default function AlphaPage() {
  const { locale } = useLocale();
  const router = useRouter();
  const [text, setText] = useState("");
  const [universe, setUniverse] = useState<FactorUniverse>("CSI500");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HypothesisTranslateResponse | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<FactorBacktestResponse | null>(null);
  // Default long_short — curated examples are statistically significant
  // in long_short but underperform cap-weighted SPY in long_only on the
  // 2024-2026 mega-cap-concentrated panel. Loading an example with
  // long_only would contradict the headline α-t / PSR claims.
  const [direction, setDirection] = useState<BacktestDirection>("long_short");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<readonly HypothesisHistoryEntry[]>([]);
  const [recent, setRecent] = useState<readonly HypothesisHistoryEntry[]>([]);
  const [allHistory, setAllHistory] = useState<readonly HypothesisHistoryEntry[]>([]);
  // v3: round-trip latency in ms — wallclock from submit → response.
  // backend reports its own runtime in smoke.runtime_ms (eval only);
  // this captures the network + LLM portion the user actually waits.
  const [translateLatencyMs, setTranslateLatencyMs] = useState<number | null>(null);

  useEffect(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
    setAllHistory(getHistory());
  }, []);

  const refreshHistory = useCallback(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
    setAllHistory(getHistory());
  }, []);

  async function onSubmit() {
    if (text.trim().length === 0) return;
    setLoading(true);
    setError(null);
    setTranslateLatencyMs(null);
    const t0 = performance.now();
    const request: HypothesisTranslateRequest = {
      text: text.trim(),
      universe,
    };
    const response = await translateHypothesis(request);
    const elapsed = performance.now() - t0;
    setLoading(false);
    if (response.error || !response.data) {
      setError(response.error ?? "Unknown error");
      setResult(null);
      setActiveId(null);
      return;
    }
    setTranslateLatencyMs(elapsed);
    const entry = addToHistory(request, response.data);
    setResult(response.data);
    setActiveId(entry.id);
    refreshHistory();
    setBacktest(null);
    setBacktestError(null);
  }

  async function onBacktest() {
    if (!result) return;
    setBacktesting(true);
    setBacktestError(null);
    const response = await runFactorBacktest({ spec: result.spec, direction });
    setBacktesting(false);
    if (response.error) {
      setBacktestError(response.error);
      setBacktest(null);
      return;
    }
    setBacktest(response.data);
  }

  const handleLoadExample = useCallback(
    (example: FactorExample) => {
      setText(locale === "zh" ? example.hypothesisZh : example.hypothesisEn);
      setResult(null);
      setBacktest(null);
      setError(null);
      setBacktestError(null);
      setActiveId(null);
    },
    [locale],
  );

  const jumpToBacktest = useCallback(() => {
    if (!result) return;
    try {
      window.sessionStorage.setItem(
        "alphacore.backtest.prefill.v1",
        JSON.stringify({
          name: result.spec.name,
          expression: result.spec.expression,
          operators_used: result.spec.operators_used,
          lookback: result.spec.lookback,
          hypothesis: result.spec.hypothesis,
        }),
      );
    } catch {
      /* sessionStorage disabled — fall through */
    }
    router.push("/backtest");
  }, [result, router]);

  const handleLoadEntry = useCallback((entry: HypothesisHistoryEntry) => {
    setText(entry.request.text);
    if (entry.request.universe) {
      setUniverse(entry.request.universe);
    }
    setResult(entry.result);
    setActiveId(entry.id);
    setError(null);
  }, []);

  const handleToggleFavorite = useCallback(
    (id: string) => {
      toggleFavorite(id);
      refreshHistory();
    },
    [refreshHistory],
  );

  const handleRemove = useCallback(
    (id: string) => {
      removeFromHistory(id);
      if (activeId === id) {
        setActiveId(null);
        setResult(null);
      }
      refreshHistory();
    },
    [activeId, refreshHistory],
  );

  const byokRequired =
    error !== null && /byok_required|X-LLM-API-Key/i.test(error);

  return (
    <TmScreen>
      <TmSubbar>
        <span className="text-tm-muted">ALPHA</span>
        <TmSubbarSep />
        <TmSubbarKV label="UNIVERSE" value={universe} />
        <TmSubbarSep />
        <TmSubbarKV label="DIRECTION" value={direction} />
        {result && (
          <>
            <TmSubbarSep />
            <TmSubbarKV
              label="IC"
              value={result.smoke.ic_spearman.toFixed(4)}
            />
            <TmSubbarSep />
            <TmSubbarKV
              label="ROWS"
              value={result.smoke.rows_valid.toString()}
            />
          </>
        )}
        <TmSubbarSpacer />
        {byokRequired && (
          <TmStatusPill tone="err">BYOK REQUIRED</TmStatusPill>
        )}
        {loading && <TmStatusPill tone="warn">TRANSLATING…</TmStatusPill>}
        {backtesting && <TmStatusPill tone="warn">BACKTESTING…</TmStatusPill>}
        {error && !byokRequired && (
          <TmStatusPill tone="err">ERROR</TmStatusPill>
        )}
        {result && (
          <ZooSaveButton
            name={result.spec.name}
            expression={result.spec.expression}
            hypothesis={result.spec.hypothesis}
            intuition={result.spec.justification}
            headlineMetrics={
              backtest
                ? {
                    testSharpe: backtest.test_metrics.sharpe,
                    totalReturn:
                      backtest.equity_curve.length > 0
                        ? backtest.equity_curve[backtest.equity_curve.length - 1]
                            .value /
                            backtest.equity_curve[0].value -
                          1
                        : undefined,
                    testIc: backtest.test_metrics.ic_spearman,
                  }
                : undefined
            }
          />
        )}
        {result && (
          <TmButton
            variant="ghost"
            onClick={jumpToBacktest}
            className="-my-1 px-2"
          >
            {t(locale, "alpha.runBacktest")}
          </TmButton>
        )}
        <TmButton
          variant="primary"
          onClick={onSubmit}
          disabled={loading || text.trim().length === 0}
          className="-my-1 px-3"
        >
          {loading ? t(locale, "alpha.submitting") : t(locale, "alpha.submit")}
        </TmButton>
      </TmSubbar>

      <HypothesisInputPane
        text={text}
        onText={setText}
        universe={universe}
        onUniverse={setUniverse}
        loading={loading}
        error={error}
        byokRequired={byokRequired}
      />

      {!result && (
        <FactorExamplesPane onLoad={handleLoadExample} />
      )}

      {result && (
        <TranslateResultPane result={result} />
      )}

      {/* v3 #1 — LLM provenance + re-translate */}
      {result && (
        <LlmProvenancePane
          result={result}
          latencyMs={translateLatencyMs}
          loading={loading}
          onRetranslate={onSubmit}
        />
      )}

      {/* v3 #2 — Expression quality scorecard */}
      {result && <ExpressionQualityPane result={result} />}

      {/* v3 #3 — Lookahead / feasibility safety check */}
      {result && <LookaheadGuardPane result={result} />}

      {result && <ASTDrawer expression={result.spec.expression} />}

      {result && (
        <BacktestQuickPane
          backtest={backtest}
          backtesting={backtesting}
          backtestError={backtestError}
          direction={direction}
          onDirection={setDirection}
          onBacktest={onBacktest}
        />
      )}

      {/* v3 #4 — History learning curve / repeat detection */}
      {allHistory.length > 0 && (
        <HistoryInsightsPane
          history={allHistory}
          currentSpec={result?.spec ?? null}
        />
      )}

      {/* v3 #5 — Operator usage across all history */}
      {allHistory.length > 0 && (
        <OperatorUsagePane history={allHistory} currentSpec={result?.spec ?? null} />
      )}

      <HypothesisHistoryPane
        favorites={favorites}
        recent={recent}
        activeId={activeId}
        onLoad={handleLoadEntry}
        onToggleFavorite={handleToggleFavorite}
        onRemove={handleRemove}
      />
    </TmScreen>
  );
}

/* ── HYPOTHESIS.INPUT pane ────────────────────────────────────────── */

function HypothesisInputPane({
  text,
  onText,
  universe,
  onUniverse,
  loading,
  error,
  byokRequired,
}: {
  readonly text: string;
  readonly onText: (v: string) => void;
  readonly universe: FactorUniverse;
  readonly onUniverse: (v: FactorUniverse) => void;
  readonly loading: boolean;
  readonly error: string | null;
  readonly byokRequired: boolean;
}) {
  const { locale } = useLocale();
  return (
    <TmPane title="HYPOTHESIS.INPUT" meta={`${text.length} CHARS`}>
      <div className="flex flex-col gap-3 px-3 py-3">
        <textarea
          value={text}
          onChange={(e) => onText(e.target.value)}
          placeholder={t(locale, "alpha.placeholder")}
          rows={3}
          spellCheck={false}
          disabled={loading}
          className="w-full resize-y border border-tm-rule bg-tm-bg-2 p-2 font-tm-mono text-[11.5px] leading-relaxed text-tm-fg outline-none transition-colors focus:border-tm-accent disabled:opacity-50"
        />
        <div className="flex flex-wrap items-end gap-3">
          <TmSelect
            label={t(locale, "alpha.universe")}
            value={universe}
            onChange={(v) => onUniverse(v as FactorUniverse)}
            options={UNIVERSE_OPTIONS.map((u) => ({
              value: u.value,
              label: u.label,
            }))}
            className="w-40"
          />
          <p className="ml-auto max-w-xl font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
            {t(locale, "alpha.tips")}
          </p>
        </div>
        {error && (
          <div className="border-t border-tm-rule pt-2.5">
            <p className="font-tm-mono text-[11px] text-tm-neg">
              {t(locale, "alpha.errorPrefix")}
              {error}
            </p>
            {byokRequired && (
              <p className="mt-1 font-tm-mono text-[11px] text-tm-muted">
                {locale === "zh"
                  ? "需要先配置你自己的 LLM API key — "
                  : "You need to configure your own LLM API key first — "}
                <a
                  href="/settings"
                  className="text-tm-accent underline hover:opacity-80"
                >
                  {locale === "zh" ? "前往设置" : "Open Settings"}
                </a>
              </p>
            )}
          </div>
        )}
      </div>
    </TmPane>
  );
}

/* ── FACTOR.EXAMPLES pane ─────────────────────────────────────────── */

function FactorExamplesPane({
  onLoad,
}: {
  readonly onLoad: (ex: FactorExample) => void;
}) {
  const { locale } = useLocale();
  return (
    <TmPane
      title="FACTOR.EXAMPLES"
      meta={`${FACTOR_EXAMPLES.length} CURATED · click loads hypothesis text`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "alpha.examples.subtitle")}
      </p>
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2 xl:grid-cols-3">
        {FACTOR_EXAMPLES.map((example) => (
          <ExampleCard key={example.name} example={example} onLoad={onLoad} />
        ))}
      </div>
    </TmPane>
  );
}

function ExampleCard({
  example,
  onLoad,
}: {
  readonly example: FactorExample;
  readonly onLoad: (e: FactorExample) => void;
}) {
  const { locale } = useLocale();
  const hypothesis =
    locale === "zh" ? example.hypothesisZh : example.hypothesisEn;
  const intuition =
    locale === "zh" ? example.intuitionZh : example.intuitionEn;
  // Tier glyph from intuition first phrase ("★ PURE ALPHA tier" /
  // "MARGINAL tier" / "NOISE tier") so each card carries its verdict.
  const tier =
    intuition.startsWith("★") || intuition.toUpperCase().includes("PURE ALPHA")
      ? { label: "PURE α", tone: "text-tm-pos border-tm-pos" }
      : intuition.toUpperCase().includes("MARGINAL")
        ? { label: "MARGINAL", tone: "text-tm-warn border-tm-warn" }
        : { label: "NOISE", tone: "text-tm-muted border-tm-rule" };
  return (
    <div className="flex flex-col gap-2 bg-tm-bg p-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-tm-mono text-[12px] font-semibold text-tm-accent">
          {example.name}
        </h3>
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block border px-1 py-px font-tm-mono text-[9.5px] tabular-nums ${tier.tone}`}
          >
            {tier.label}
          </span>
          <span className="border border-tm-accent bg-tm-accent-soft px-1.5 py-px font-tm-mono text-[10.5px] tabular-nums text-tm-accent">
            {example.totalReturn >= 0 ? "+" : ""}
            {(example.totalReturn * 100).toFixed(1)}%
          </span>
        </div>
      </div>
      <p className="font-tm-mono text-[11px] leading-relaxed text-tm-fg">
        {hypothesis}
      </p>
      <code className="block overflow-x-auto border border-tm-rule bg-tm-bg-2 px-2 py-1 font-tm-mono text-[10.5px] text-tm-fg-2">
        {example.expression}
      </code>
      <p className="line-clamp-3 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {intuition}
      </p>
      <div className="mt-1 flex items-center justify-between gap-2 border-t border-tm-rule pt-2">
        <div className="flex gap-3 font-tm-mono text-[10.5px] text-tm-muted">
          <span>
            {t(locale, "alpha.examples.sharpeLabel")}:{" "}
            <span className="tabular-nums text-tm-fg">
              {example.testSharpe.toFixed(2)}
            </span>
          </span>
          <span>
            IC:{" "}
            <span className="tabular-nums text-tm-fg">
              {example.testIC.toFixed(3)}
            </span>
          </span>
        </div>
        <TmButton
          variant="ghost"
          onClick={() => onLoad(example)}
          className="h-6 px-2 text-[10px]"
        >
          {t(locale, "alpha.examples.useBtn")}
        </TmButton>
      </div>
    </div>
  );
}

/* ── TRANSLATE.RESULT pane ────────────────────────────────────────── */

function TranslateResultPane({
  result,
}: {
  readonly result: HypothesisTranslateResponse;
}) {
  const { locale } = useLocale();
  const icAccent =
    Math.abs(result.smoke.ic_spearman) >= 0.03 ? "pos" : "default";
  return (
    <TmCols2>
      <TmPane title="TRANSLATE.SPEC" meta="LLM → FactorSpec">
        <dl
          className="grid gap-px bg-tm-rule font-tm-mono text-[11px]"
          style={{ gridTemplateColumns: "minmax(110px, 130px) 1fr" }}
        >
          <SpecRow label={t(locale, "alpha.labelName")} value={result.spec.name} mono />
          <SpecRow
            label={t(locale, "alpha.labelHypothesis")}
            value={result.spec.hypothesis}
          />
          <SpecRow
            label={t(locale, "alpha.labelExpression")}
            value={result.spec.expression}
            mono
          />
          <SpecRow
            label={t(locale, "alpha.labelOperators")}
            value={result.spec.operators_used.join(", ")}
            mono
          />
          <SpecRow
            label={t(locale, "alpha.labelLookback")}
            value={`${result.spec.lookback} days`}
          />
          <SpecRow
            label={t(locale, "alpha.labelUniverse")}
            value={result.spec.universe}
          />
          <SpecRow
            label={t(locale, "alpha.labelJustification")}
            value={result.spec.justification}
          />
        </dl>
      </TmPane>
      <TmPane title="SMOKE.PROBE" meta="synthetic-panel sanity check">
        <TmKpiGrid>
          <TmKpi
            label={t(locale, "alpha.labelIC")}
            value={result.smoke.ic_spearman.toFixed(4)}
            tone={icAccent}
            sub="rank IC threshold ±0.03"
          />
          <TmKpi
            label={t(locale, "alpha.labelRows")}
            value={result.smoke.rows_valid.toString()}
            sub="non-NaN cells"
          />
          <TmKpi
            label={t(locale, "alpha.labelRuntime")}
            value={`${result.smoke.runtime_ms.toFixed(1)}ms`}
            sub="server-side eval"
          />
          <TmKpi
            label={t(locale, "alpha.labelTokens")}
            value={`${result.llm_tokens.prompt}+${result.llm_tokens.completion}`}
            sub="prompt + completion"
          />
        </TmKpiGrid>
      </TmPane>
    </TmCols2>
  );
}

function SpecRow({
  label,
  value,
  mono,
}: {
  readonly label: string;
  readonly value: string;
  readonly mono?: boolean;
}) {
  return (
    <>
      <dt className="bg-tm-bg-2 px-2 py-1.5 text-[10px] uppercase tracking-[0.06em] text-tm-muted">
        {label}
      </dt>
      <dd
        className={`bg-tm-bg px-2 py-1.5 ${mono ? "break-all text-tm-accent" : "text-tm-fg"}`}
      >
        {value}
      </dd>
    </>
  );
}

/* ── BACKTEST.QUICK pane ──────────────────────────────────────────── */

function BacktestQuickPane({
  backtest,
  backtesting,
  backtestError,
  direction,
  onDirection,
  onBacktest,
}: {
  readonly backtest: FactorBacktestResponse | null;
  readonly backtesting: boolean;
  readonly backtestError: string | null;
  readonly direction: BacktestDirection;
  readonly onDirection: (d: BacktestDirection) => void;
  readonly onBacktest: () => void;
}) {
  const { locale } = useLocale();
  const totalReturn =
    backtest && backtest.equity_curve.length > 0
      ? backtest.equity_curve[backtest.equity_curve.length - 1].value /
          backtest.equity_curve[0].value -
        1
      : null;
  return (
    <TmPane
      title="BACKTEST.QUICK"
      meta={
        backtest
          ? `train SR ${backtest.train_metrics.sharpe.toFixed(2)} · test SR ${backtest.test_metrics.sharpe.toFixed(2)}`
          : "configure direction + run"
      }
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "alpha.backtest.subtitle")}
      </p>
      <div className="flex flex-wrap items-center gap-3 border-b border-tm-rule bg-tm-bg-2 px-3 py-2">
        <span className="font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
          {t(locale, "alpha.backtest.directionLabel")}
        </span>
        {(["long_only", "long_short", "short_only"] as const).map((dir) => (
          <TmChip
            key={dir}
            on={direction === dir}
            onClick={() => onDirection(dir)}
          >
            {t(
              locale,
              dir === "long_only"
                ? "alpha.backtest.dirLongOnly"
                : dir === "long_short"
                  ? "alpha.backtest.dirLongShort"
                  : "alpha.backtest.dirShortOnly",
            )}
          </TmChip>
        ))}
        <span className="font-tm-mono text-[10px] text-tm-muted">
          {t(locale, DIRECTION_HELP_KEY[direction])}
        </span>
        <TmButton
          variant="primary"
          onClick={onBacktest}
          disabled={backtesting}
          className="ml-auto"
        >
          {backtesting
            ? t(locale, "alpha.backtest.running")
            : t(locale, "alpha.backtest.run")}
        </TmButton>
      </div>

      {backtestError && (
        <p className="px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
          {t(locale, "alpha.backtest.errorPrefix")}
          {backtestError}
        </p>
      )}

      {backtest && (
        <>
          <TmKpiGrid>
            <TmKpi
              label={t(locale, "alpha.backtest.trainSharpe")}
              value={backtest.train_metrics.sharpe.toFixed(2)}
              tone={
                backtest.train_metrics.sharpe > 0
                  ? "pos"
                  : backtest.train_metrics.sharpe < 0
                    ? "neg"
                    : "default"
              }
              sub="in-sample"
            />
            <TmKpi
              label={t(locale, "alpha.backtest.testSharpe")}
              value={backtest.test_metrics.sharpe.toFixed(2)}
              tone={
                backtest.test_metrics.sharpe >= 1.0
                  ? "pos"
                  : backtest.test_metrics.sharpe <= 0
                    ? "neg"
                    : "default"
              }
              sub="out-of-sample"
            />
            <TmKpi
              label={t(locale, "alpha.backtest.trainIC")}
              value={backtest.train_metrics.ic_spearman.toFixed(4)}
              sub="rank IC"
            />
            <TmKpi
              label={t(locale, "alpha.backtest.testIC")}
              value={backtest.test_metrics.ic_spearman.toFixed(4)}
              tone={
                backtest.test_metrics.ic_spearman > 0 ? "pos" : "neg"
              }
              sub="rank IC"
            />
            <TmKpi
              label={t(locale, "alpha.backtest.trainReturn")}
              value={`${(backtest.train_metrics.total_return * 100).toFixed(2)}%`}
              tone={
                backtest.train_metrics.total_return > 0 ? "pos" : "neg"
              }
            />
            <TmKpi
              label={t(locale, "alpha.backtest.testReturn")}
              value={`${(backtest.test_metrics.total_return * 100).toFixed(2)}%`}
              tone={
                backtest.test_metrics.total_return > 0 ? "pos" : "neg"
              }
              sub={
                totalReturn != null
                  ? `full ${(totalReturn * 100).toFixed(1)}%`
                  : undefined
              }
            />
          </TmKpiGrid>
          <div className="px-2 pb-2 pt-2">
            <FactorPnLChart data={backtest} height={300} />
          </div>
        </>
      )}
    </TmPane>
  );
}

/* ── v3 #1 — LLM.PROVENANCE pane ─────────────────────────────────── */

const TOKEN_PRICING_USD_PER_1M: Record<string, { prompt: number; completion: number }> = {
  // Approximate retail pricing for transparency. Treat as estimate, not invoice.
  openai: { prompt: 2.50, completion: 10.00 }, // gpt-4o
  kimi: { prompt: 0.30, completion: 0.30 },
  anthropic: { prompt: 3.00, completion: 15.00 }, // claude sonnet 4.6
  ollama: { prompt: 0, completion: 0 }, // self-hosted
};

function LlmProvenancePane({
  result,
  latencyMs,
  loading,
  onRetranslate,
}: {
  readonly result: HypothesisTranslateResponse;
  readonly latencyMs: number | null;
  readonly loading: boolean;
  readonly onRetranslate: () => void;
}) {
  const [byok, setByok] = useState<ByokGetResponse | null>(null);
  useEffect(() => {
    getByok().then(setByok).catch(() => setByok(null));
  }, []);
  const rawProvider = byok?.provider;
  const provider: LLMProvider | undefined =
    rawProvider && rawProvider in PROVIDER_PRESETS
      ? (rawProvider as LLMProvider)
      : undefined;
  const providerLabel = provider ? PROVIDER_PRESETS[provider].label : "platform default";
  const model = byok?.model || (provider ? PROVIDER_PRESETS[provider].defaultModel : "—");
  const totalTokens = result.llm_tokens.prompt + result.llm_tokens.completion;
  const pricing = provider ? TOKEN_PRICING_USD_PER_1M[provider] : null;
  const cost =
    pricing && (pricing.prompt > 0 || pricing.completion > 0)
      ? (result.llm_tokens.prompt * pricing.prompt +
          result.llm_tokens.completion * pricing.completion) / 1_000_000
      : null;
  return (
    <TmPane title="LLM.PROVENANCE" meta="provider · model · cost · latency">
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Translation came from BYOK {providerLabel}. Cost is an estimate using retail-tier list price; actual billing depends on your provider tier and bulk discounts.
      </p>
      <TmKpiGrid>
        <TmKpi
          label="PROVIDER"
          value={providerLabel}
          sub={provider ?? "no key configured"}
        />
        <TmKpi
          label="MODEL"
          value={model.length > 22 ? model.slice(0, 21) + "…" : model}
          sub="via BYOK config"
        />
        <TmKpi
          label="TOKENS"
          value={totalTokens.toString()}
          sub={`${result.llm_tokens.prompt} prompt + ${result.llm_tokens.completion} completion`}
        />
        <TmKpi
          label="COST EST"
          value={cost != null ? `$${cost.toFixed(4)}` : "—"}
          tone={cost != null && cost > 0.01 ? "warn" : "default"}
          sub={cost != null ? "USD this run" : "self-hosted / unknown"}
        />
        <TmKpi
          label="LATENCY"
          value={latencyMs != null ? `${(latencyMs / 1000).toFixed(2)}s` : "—"}
          sub="round-trip wallclock"
        />
        <TmKpi
          label="EVAL"
          value={`${result.smoke.runtime_ms.toFixed(0)}ms`}
          sub="server-side smoke eval"
        />
      </TmKpiGrid>
      <div className="flex items-center justify-between border-t border-tm-rule bg-tm-bg-2 px-3 py-1.5">
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          Same hypothesis text → same prompt, but LLM is non-deterministic. Re-translate to see how stable the spec is across runs.
        </span>
        <TmButton
          variant="ghost"
          onClick={onRetranslate}
          disabled={loading}
          className="h-6 px-2 text-[10px]"
        >
          {loading ? "running…" : "↻ re-translate"}
        </TmButton>
      </div>
    </TmPane>
  );
}

/* ── v3 #2 — EXPRESSION.QUALITY pane ─────────────────────────────── */

// Operator family classification — used by quality scorecard + operator
// usage analytics. Each operator maps to one family; unmapped ops fall
// to "other".
const OP_FAMILY_MAP: Record<string, string> = {
  rank: "cross-section", zscore: "cross-section",
  group_neutralize: "cross-section", winsorize: "cross-section",
  ts_mean: "time-series", ts_std: "time-series", ts_zscore: "time-series",
  ts_rank: "time-series", ts_min: "time-series", ts_max: "time-series",
  ts_sum: "time-series", ts_corr: "time-series", ts_argmax: "time-series",
  ts_argmin: "time-series", ts_decay_linear: "time-series",
  add: "math", subtract: "math", multiply: "math", divide: "math",
  sub: "math", div: "math", mul: "math",
  log: "math", abs: "math", sqrt: "math", power: "math",
  sign: "math", inverse: "math", neg: "math",
  greater: "logic", less: "logic", greater_equal: "logic",
  less_equal: "logic", equal: "logic",
  if_else: "logic", and: "logic", or: "logic",
  // Time-series operators with horizon argument typically appear with
  // numeric literal as second arg — handled in depth/horizon parsing.
};

function classifyFamily(op: string): string {
  return OP_FAMILY_MAP[op] ?? "other";
}

// Approximate AST depth: count maximum nested parentheses in expression.
function exprDepth(expression: string): number {
  let depth = 0;
  let max = 0;
  for (const ch of expression) {
    if (ch === "(") {
      depth += 1;
      if (depth > max) max = depth;
    } else if (ch === ")") {
      depth -= 1;
    }
  }
  return max;
}

// Find largest numeric literal in expression — used as a proxy for the
// max horizon required by ts_* operators (ts_mean(returns, 252) → 252).
function maxNumericLiteral(expression: string): number {
  const matches = expression.match(/\b\d+\b/g);
  if (!matches) return 0;
  let m = 0;
  for (const s of matches) {
    const n = parseInt(s, 10);
    if (Number.isFinite(n) && n > m) m = n;
  }
  return m;
}

function ExpressionQualityPane({
  result,
}: {
  readonly result: HypothesisTranslateResponse;
}) {
  const stats = useMemo(() => {
    const expr = result.spec.expression;
    const ops = [...extractOps(expr)];
    const uniqueOps = Array.from(new Set(ops));
    const families = Array.from(new Set(uniqueOps.map(classifyFamily)));
    const depth = exprDepth(expr);
    const opCount = ops.length;
    const uniqueRatio = opCount > 0 ? uniqueOps.length / opCount : 0;
    const maxHorizon = maxNumericLiteral(expr);
    const declaredLookback = result.spec.lookback;
    const horizonOk = maxHorizon === 0 || declaredLookback >= maxHorizon || maxHorizon <= 252;
    // Composite score 0-100. Penalize: very low op count (toy expr),
    // very high depth (likely overfit / brittle), very low unique-op
    // ratio (repetition), incoherent lookback.
    let score = 100;
    if (opCount < 2) score -= 30; // toy
    if (opCount > 12) score -= 15; // bloated
    if (depth > 5) score -= 20; // brittle nesting
    if (uniqueRatio < 0.5 && opCount > 3) score -= 15;
    if (!horizonOk) score -= 25;
    if (families.length === 1 && opCount > 3) score -= 10; // monoculture
    score = Math.max(0, Math.min(100, score));
    const grade =
      score >= 85 ? "A" :
      score >= 75 ? "B" :
      score >= 60 ? "C" :
      score >= 45 ? "D" : "F";
    return {
      ops,
      uniqueOps,
      families,
      depth,
      opCount,
      uniqueRatio,
      maxHorizon,
      horizonOk,
      score,
      grade,
    };
  }, [result]);

  const gradeTone =
    stats.grade === "A" ? "pos" :
    stats.grade === "B" ? "pos" :
    stats.grade === "C" ? "default" :
    stats.grade === "D" ? "warn" : "neg";

  return (
    <TmPane
      title="EXPRESSION.QUALITY"
      meta={`grade ${stats.grade} · score ${stats.score}/100`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Static scorecard from the expression AST. Penalties for very-shallow / very-deep nesting, op repetition, family monoculture, and lookback mismatch. Score is a proxy for &quot;is this likely to backtest stably&quot; — high score does not guarantee positive α.
      </p>
      <TmKpiGrid>
        <TmKpi
          label="GRADE"
          value={stats.grade}
          tone={gradeTone}
          sub={`${stats.score}/100 composite`}
        />
        <TmKpi
          label="DEPTH"
          value={stats.depth.toString()}
          tone={stats.depth > 5 ? "warn" : stats.depth < 1 ? "warn" : "default"}
          sub="max paren nesting"
        />
        <TmKpi
          label="OP COUNT"
          value={stats.opCount.toString()}
          tone={stats.opCount < 2 ? "warn" : stats.opCount > 12 ? "warn" : "default"}
          sub={`${stats.uniqueOps.length} unique`}
        />
        <TmKpi
          label="UNIQUE %"
          value={`${(stats.uniqueRatio * 100).toFixed(0)}%`}
          tone={stats.uniqueRatio < 0.5 ? "warn" : "default"}
          sub="non-repeated ops"
        />
        <TmKpi
          label="FAMILIES"
          value={stats.families.length.toString()}
          tone={stats.families.length === 1 ? "warn" : "default"}
          sub={stats.families.join(" · ")}
        />
        <TmKpi
          label="MAX HORIZON"
          value={stats.maxHorizon === 0 ? "—" : `${stats.maxHorizon}d`}
          tone={!stats.horizonOk ? "warn" : "default"}
          sub={`vs lookback ${result.spec.lookback}d`}
        />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── v3 #3 — LOOKAHEAD.GUARD pane ────────────────────────────────── */

// Operators that strictly look at past data — used to detect lookahead
// hazards. Anything in `forwardRefOps` would be a red flag if backend
// added it (currently none, but defensive listing).
const PAST_LOOKING_OPS = new Set([
  "ts_mean", "ts_std", "ts_zscore", "ts_rank", "ts_min", "ts_max",
  "ts_sum", "ts_corr", "ts_argmax", "ts_argmin", "ts_decay_linear",
]);
const FORWARD_LOOKING_OPS = new Set<string>([
  // None today — placeholder for future detection.
]);
// Panel fields the engine recognizes. Any expression token not matching
// an operator, literal, or this set is suspicious.
const PANEL_FIELDS = new Set([
  "close", "open", "high", "low", "volume",
  "returns", "dollar_volume", "adv60",
  "cap", "sector", "industry", "shares_outstanding",
  "revenue", "net_income_adjusted", "ebitda", "eps",
  "equity", "assets", "free_cash_flow", "gross_profit",
  "operating_income", "cost_of_goods_sold", "ebit",
  "current_assets", "current_liabilities",
  "long_term_debt", "short_term_debt",
  "cash_and_equivalents", "retained_earnings", "goodwill",
  "operating_cash_flow", "investing_cash_flow",
  "total_liabilities",
]);

function LookaheadGuardPane({
  result,
}: {
  readonly result: HypothesisTranslateResponse;
}) {
  const checks = useMemo(() => {
    const expr = result.spec.expression;
    const ops = [...extractOps(expr)];
    const tokens = expr.match(/\b[a-zA-Z_][a-zA-Z0-9_]*\b/g) ?? [];
    // Identify field references by removing operator names and known
    // identifiers.
    const opSet = new Set(ops);
    const fieldRefs = Array.from(new Set(
      tokens.filter((tk) => !opSet.has(tk) && tk !== "true" && tk !== "false")
    ));
    const knownFields = fieldRefs.filter((f) => PANEL_FIELDS.has(f));
    const unknownFields = fieldRefs.filter((f) => !PANEL_FIELDS.has(f));
    const forwardOps = ops.filter((op) => FORWARD_LOOKING_OPS.has(op));
    const pastOps = ops.filter((op) => PAST_LOOKING_OPS.has(op));
    const maxHorizon = maxNumericLiteral(expr);
    const declaredLookback = result.spec.lookback;
    const horizonExceedsLookback = maxHorizon > declaredLookback && maxHorizon > 0;
    const horizonExceedsTradingYear = maxHorizon > 252;

    const checks: { label: string; pass: boolean; detail: string }[] = [
      {
        label: "no forward-looking ops",
        pass: forwardOps.length === 0,
        detail: forwardOps.length === 0
          ? "all ops are past-window only"
          : `forward-looking detected: ${forwardOps.join(", ")}`,
      },
      {
        label: "all fields panel-resident",
        pass: unknownFields.length === 0,
        detail: unknownFields.length === 0
          ? `${knownFields.length} known fields`
          : `unknown: ${unknownFields.slice(0, 3).join(", ")}${unknownFields.length > 3 ? "…" : ""}`,
      },
      {
        label: "horizon ≤ trading year",
        pass: !horizonExceedsTradingYear,
        detail: maxHorizon === 0
          ? "no horizon literal"
          : `max horizon ${maxHorizon}d ${horizonExceedsTradingYear ? "(exceeds 252d)" : "(≤ 252d)"}`,
      },
      {
        label: "horizon ≤ declared lookback",
        pass: !horizonExceedsLookback,
        detail: maxHorizon === 0
          ? "no horizon literal"
          : `${maxHorizon}d ${horizonExceedsLookback ? ">" : "≤"} ${declaredLookback}d declared`,
      },
      {
        label: "operator stack non-empty",
        pass: ops.length > 0,
        detail: `${ops.length} operators · ${pastOps.length} past-window`,
      },
    ];
    return { checks, pastOps, fieldRefs, unknownFields };
  }, [result]);
  const passed = checks.checks.filter((c) => c.pass).length;
  const total = checks.checks.length;
  const allPass = passed === total;
  return (
    <TmPane
      title="LOOKAHEAD.GUARD"
      meta={`${passed}/${total} checks passed${allPass ? "" : " · ⚠"}`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Static safety + feasibility checks before backtest. Operator-stack scan + panel-field cross-check + horizon-vs-lookback consistency. A passed check does not certify the factor works — only that it will not silently fail at evaluation time.
      </p>
      <ul className="flex flex-col">
        {checks.checks.map((c) => (
          <li
            key={c.label}
            className="grid items-center gap-3 border-b border-tm-rule px-3 py-1.5 last:border-b-0"
            style={{ gridTemplateColumns: "24px minmax(180px, 220px) 1fr" }}
          >
            <span
              className={`text-center font-tm-mono text-[12px] ${c.pass ? "text-tm-pos" : "text-tm-warn"}`}
            >
              {c.pass ? "✓" : "▸"}
            </span>
            <span className="font-tm-mono text-[11px] text-tm-fg">
              {c.label}
            </span>
            <span className="font-tm-mono text-[10.5px] text-tm-muted">
              {c.detail}
            </span>
          </li>
        ))}
      </ul>
    </TmPane>
  );
}

/* ── v3 #4 — HISTORY.INSIGHTS pane ───────────────────────────────── */

function HistoryInsightsPane({
  history,
  currentSpec,
}: {
  readonly history: readonly HypothesisHistoryEntry[];
  readonly currentSpec: HypothesisTranslateResponse["spec"] | null;
}) {
  const stats = useMemo(() => {
    const total = history.length;
    const ics = history
      .map((h) => h.result?.smoke.ic_spearman)
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    const meanIC = ics.length > 0 ? ics.reduce((a, b) => a + b, 0) / ics.length : 0;
    const medianIC = ics.length > 0
      ? [...ics].sort((a, b) => a - b)[Math.floor(ics.length / 2)]
      : 0;
    // Trend: split history into halves, compare avg IC.
    const half = Math.floor(history.length / 2);
    const first = history.slice(0, half).map((h) => h.result?.smoke.ic_spearman).filter((v): v is number => typeof v === "number");
    const second = history.slice(half).map((h) => h.result?.smoke.ic_spearman).filter((v): v is number => typeof v === "number");
    const firstAvg = first.length > 0 ? first.reduce((a, b) => a + b, 0) / first.length : 0;
    const secondAvg = second.length > 0 ? second.reduce((a, b) => a + b, 0) / second.length : 0;
    const trendDelta = secondAvg - firstAvg;
    // Repeat detection: count entries with same hypothesis text.
    const textCount = new Map<string, number>();
    for (const h of history) {
      const k = h.request.text.trim().toLowerCase();
      textCount.set(k, (textCount.get(k) ?? 0) + 1);
    }
    const repeats = Array.from(textCount.values()).filter((c) => c > 1).length;
    const repeatRate = total > 0 ? repeats / textCount.size : 0;
    // Current vs historical: how does the current spec's smoke IC rank?
    let currentRank: number | null = null;
    if (currentSpec) {
      const currentIC = history.find((h) => h.result?.spec.expression === currentSpec.expression)
        ?.result?.smoke.ic_spearman;
      if (currentIC != null && ics.length > 0) {
        const better = ics.filter((v) => v < currentIC).length;
        currentRank = (better / ics.length) * 100;
      }
    }
    return {
      total,
      meanIC,
      medianIC,
      trendDelta,
      repeats,
      repeatRate,
      uniqueHypotheses: textCount.size,
      currentRank,
    };
  }, [history, currentSpec]);
  return (
    <TmPane
      title="HISTORY.INSIGHTS"
      meta={`${stats.total} translations · ${stats.uniqueHypotheses} unique`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Aggregated stats across your translation history. Trend delta = second-half mean IC − first-half mean IC. Positive trend suggests refinement learning curve; near-zero suggests noise.
      </p>
      <TmKpiGrid>
        <TmKpi
          label="TRANSLATIONS"
          value={stats.total.toString()}
          sub={`${stats.uniqueHypotheses} unique inputs`}
        />
        <TmKpi
          label="MEAN IC"
          value={stats.meanIC.toFixed(4)}
          tone={stats.meanIC > 0 ? "pos" : "neg"}
          sub="across all runs"
        />
        <TmKpi
          label="MEDIAN IC"
          value={stats.medianIC.toFixed(4)}
          tone={stats.medianIC > 0 ? "pos" : "neg"}
          sub="robust to outliers"
        />
        <TmKpi
          label="TREND Δ"
          value={`${stats.trendDelta >= 0 ? "+" : ""}${stats.trendDelta.toFixed(4)}`}
          tone={stats.trendDelta > 0 ? "pos" : stats.trendDelta < 0 ? "neg" : "default"}
          sub="2nd half − 1st half"
        />
        <TmKpi
          label="REPEAT RATE"
          value={`${(stats.repeatRate * 100).toFixed(0)}%`}
          tone={stats.repeatRate > 0.3 ? "warn" : "default"}
          sub={`${stats.repeats} repeated`}
        />
        <TmKpi
          label="THIS RUN PCT"
          value={stats.currentRank != null ? `${stats.currentRank.toFixed(0)}p` : "—"}
          tone={
            stats.currentRank == null ? "default"
            : stats.currentRank > 75 ? "pos"
            : stats.currentRank < 25 ? "neg" : "default"
          }
          sub="vs your history"
        />
      </TmKpiGrid>
    </TmPane>
  );
}

/* ── v3 #5 — OPERATOR.USAGE pane ─────────────────────────────────── */

const TOP_OPS_DISPLAY = 10;

function OperatorUsagePane({
  history,
  currentSpec,
}: {
  readonly history: readonly HypothesisHistoryEntry[];
  readonly currentSpec: HypothesisTranslateResponse["spec"] | null;
}) {
  const stats = useMemo(() => {
    const counts = new Map<string, number>();
    const familyCounts = new Map<string, number>();
    for (const h of history) {
      const expr = h.result?.spec.expression ?? "";
      const ops = expr ? [...extractOps(expr)] : [];
      const seen = new Set<string>();
      for (const op of ops) {
        if (seen.has(op)) continue;
        seen.add(op);
        counts.set(op, (counts.get(op) ?? 0) + 1);
        const fam = classifyFamily(op);
        familyCounts.set(fam, (familyCounts.get(fam) ?? 0) + 1);
      }
    }
    const ranked = Array.from(counts.entries())
      .map(([op, count]) => ({
        op,
        count,
        share: history.length > 0 ? count / history.length : 0,
        family: classifyFamily(op),
      }))
      .sort((a, b) => b.count - a.count)
      .slice(0, TOP_OPS_DISPLAY);
    const familyRanked = Array.from(familyCounts.entries())
      .map(([family, count]) => ({
        family,
        count,
        share: history.length > 0 ? count / history.length : 0,
      }))
      .sort((a, b) => b.count - a.count);
    const totalFamilyShare = familyRanked.reduce((a, f) => a + f.share, 0);
    const concentration = familyRanked.length > 0 && totalFamilyShare > 0
      ? familyRanked[0].share / totalFamilyShare
      : 0;
    return { ranked, familyRanked, concentration };
  }, [history]);
  const currentOps = currentSpec
    ? new Set([...extractOps(currentSpec.expression)])
    : new Set<string>();
  const concentrationWarn = stats.concentration > 0.6;
  return (
    <TmPane
      title="OPERATOR.USAGE"
      meta={`top ${stats.ranked.length} of ${stats.ranked.length} unique · ${stats.familyRanked.length} families${concentrationWarn ? " · ⚠ concentrated" : ""}`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        Operator frequency across your translation history. Highlighted = used in the current spec. Family concentration ≥ 60% (one family dominates) flags possible single-style monoculture in your factor research.
      </p>
      {stats.ranked.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
          no operators detected in history yet.
        </p>
      ) : (
        <ul className="flex flex-col">
          {stats.ranked.map((row, i) => {
            const isCurrent = currentOps.has(row.op);
            const widthPct = (row.share * 100);
            return (
              <li
                key={row.op}
                className={`grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0 ${isCurrent ? "bg-tm-accent-soft" : ""}`}
                style={{ gridTemplateColumns: "24px minmax(120px, 140px) minmax(110px, 130px) 1fr 60px 50px" }}
              >
                <span className="text-center font-tm-mono text-[10px] text-tm-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className={`truncate font-tm-mono text-[11px] ${isCurrent ? "text-tm-accent" : "text-tm-fg"}`}>
                  {row.op}
                </span>
                <span className="font-tm-mono text-[10px] text-tm-muted">
                  {row.family}
                </span>
                <div className="relative h-3 w-full bg-tm-bg-2">
                  <div
                    className={`h-full opacity-60 ${isCurrent ? "bg-tm-accent" : "bg-tm-fg-2"}`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
                  {row.count}
                </span>
                <span className="text-right font-tm-mono text-[10px] tabular-nums text-tm-muted">
                  {(row.share * 100).toFixed(0)}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {stats.familyRanked.length > 0 && (
        <>
          <div className="border-t border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
            FAMILY DISTRIBUTION · concentration {(stats.concentration * 100).toFixed(0)}%
          </div>
          <ul className="flex flex-col">
            {stats.familyRanked.map((f) => (
              <li
                key={f.family}
                className="grid items-center gap-3 border-b border-tm-rule px-3 py-1 last:border-b-0"
                style={{ gridTemplateColumns: "minmax(140px, 160px) 1fr 60px 50px" }}
              >
                <span className={`font-tm-mono text-[11px] ${concentrationWarn && f === stats.familyRanked[0] ? "text-tm-warn" : "text-tm-info"}`}>
                  {f.family}
                </span>
                <div className="relative h-3 w-full bg-tm-bg-2">
                  <div
                    className={`h-full opacity-60 ${concentrationWarn && f === stats.familyRanked[0] ? "bg-tm-warn" : "bg-tm-info"}`}
                    style={{ width: `${f.share * 100}%` }}
                  />
                </div>
                <span className="text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg-2">
                  {f.count}
                </span>
                <span className="text-right font-tm-mono text-[10px] tabular-nums text-tm-muted">
                  {(f.share * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </TmPane>
  );
}

/* ── HYPOTHESIS.HISTORY pane ──────────────────────────────────────── */

function HypothesisHistoryPane({
  favorites,
  recent,
  activeId,
  onLoad,
  onToggleFavorite,
  onRemove,
}: {
  readonly favorites: readonly HypothesisHistoryEntry[];
  readonly recent: readonly HypothesisHistoryEntry[];
  readonly activeId: string | null;
  readonly onLoad: (entry: HypothesisHistoryEntry) => void;
  readonly onToggleFavorite: (id: string) => void;
  readonly onRemove: (id: string) => void;
}) {
  const { locale } = useLocale();
  if (favorites.length === 0 && recent.length === 0) return null;
  return (
    <TmPane
      title="HYPOTHESIS.HISTORY"
      meta={`${favorites.length} starred · ${recent.length} recent`}
    >
      <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2">
        <HistorySection
          title={t(locale, "alpha.historyFavorites")}
          entries={favorites}
          activeId={activeId}
          onLoad={onLoad}
          onToggleFavorite={onToggleFavorite}
          onRemove={onRemove}
          emptyKey="alpha.historyEmpty"
          starredSection
        />
        <HistorySection
          title={t(locale, "alpha.historyRecent")}
          entries={recent}
          activeId={activeId}
          onLoad={onLoad}
          onToggleFavorite={onToggleFavorite}
          onRemove={onRemove}
          emptyKey="alpha.historyEmpty"
          starredSection={false}
        />
      </div>
    </TmPane>
  );
}

function HistorySection({
  title,
  entries,
  activeId,
  onLoad,
  onToggleFavorite,
  onRemove,
  emptyKey,
  starredSection,
}: {
  readonly title: string;
  readonly entries: readonly HypothesisHistoryEntry[];
  readonly activeId: string | null;
  readonly onLoad: (e: HypothesisHistoryEntry) => void;
  readonly onToggleFavorite: (id: string) => void;
  readonly onRemove: (id: string) => void;
  readonly emptyKey: TranslationKey;
  readonly starredSection: boolean;
}) {
  const { locale } = useLocale();
  return (
    <div className="flex flex-col bg-tm-bg">
      <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {title} · {entries.length}
      </div>
      {entries.length === 0 ? (
        <p className="px-3 py-3 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, emptyKey)}
        </p>
      ) : (
        <ul className="flex flex-col">
          {entries.map((e) => (
            <HistoryRow
              key={e.id}
              entry={e}
              isActive={e.id === activeId}
              onLoad={() => onLoad(e)}
              onToggleFavorite={() => onToggleFavorite(e.id)}
              onRemove={() => onRemove(e.id)}
              starred={starredSection || e.isFavorite}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function HistoryRow({
  entry,
  isActive,
  onLoad,
  onToggleFavorite,
  onRemove,
  starred,
}: {
  readonly entry: HypothesisHistoryEntry;
  readonly isActive: boolean;
  readonly onLoad: () => void;
  readonly onToggleFavorite: () => void;
  readonly onRemove: () => void;
  readonly starred: boolean;
}) {
  const { locale } = useLocale();
  const ago = formatTimeAgo(entry.timestamp, locale);
  return (
    <li
      className={`flex flex-col gap-1 border-b border-tm-rule px-3 py-1.5 last:border-b-0 ${
        isActive ? "bg-tm-accent-soft" : ""
      }`}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleFavorite}
          className={`font-tm-mono text-[11px] ${starred ? "text-tm-warn" : "text-tm-muted hover:text-tm-warn"}`}
          title={starred ? "unstar" : "star"}
        >
          {starred ? "★" : "☆"}
        </button>
        <button
          type="button"
          onClick={onLoad}
          className={`flex-1 truncate text-left font-tm-mono text-[11px] ${
            isActive ? "text-tm-accent" : "text-tm-fg hover:text-tm-accent"
          }`}
          title={entry.request.text}
        >
          {entry.request.text}
        </button>
        <span className="shrink-0 font-tm-mono text-[10px] text-tm-muted">
          {ago}
        </span>
        <button
          type="button"
          onClick={onRemove}
          className="font-tm-mono text-[10px] text-tm-muted hover:text-tm-neg"
          title="remove"
        >
          ×
        </button>
      </div>
      {entry.result?.spec.expression && (
        <code className="ml-5 block truncate font-tm-mono text-[10px] text-tm-fg-2">
          {entry.result.spec.expression}
        </code>
      )}
    </li>
  );
}

function formatTimeAgo(iso: string, locale: "zh" | "en"): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));
  const isZh = locale === "zh";
  if (diffSec < 60) return isZh ? "刚刚" : "just now";
  const min = Math.floor(diffSec / 60);
  if (min < 60) return isZh ? `${min} 分钟前` : `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return isZh ? `${h} 小时前` : `${h}h ago`;
  const d = Math.floor(h / 24);
  return isZh ? `${d} 天前` : `${d}d ago`;
}
