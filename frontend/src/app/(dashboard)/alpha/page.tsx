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

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
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

  useEffect(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
  }, []);

  const refreshHistory = useCallback(() => {
    setFavorites(getFavorites());
    setRecent(getRecent());
  }, []);

  async function onSubmit() {
    if (text.trim().length === 0) return;
    setLoading(true);
    setError(null);
    const request: HypothesisTranslateRequest = {
      text: text.trim(),
      universe,
    };
    const response = await translateHypothesis(request);
    setLoading(false);
    if (response.error || !response.data) {
      setError(response.error ?? "Unknown error");
      setResult(null);
      setActiveId(null);
      return;
    }
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
