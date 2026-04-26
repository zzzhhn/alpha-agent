"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import { HypothesisHistoryPanel } from "@/components/alpha/HypothesisHistoryPanel";
import { ZooSaveButton } from "@/components/zoo/ZooSaveButton";
import {
  FactorExamples,
  type FactorExample,
} from "@/components/alpha/FactorExamples";
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

const UNIVERSES: readonly { value: FactorUniverse; label: string }[] = [
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
  const [direction, setDirection] = useState<BacktestDirection>("long_only");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<readonly HypothesisHistoryEntry[]>(
    [],
  );
  const [recent, setRecent] = useState<readonly HypothesisHistoryEntry[]>([]);

  // Hydrate from localStorage after mount (SSR-safe)
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
    // A new spec invalidates the previous backtest result.
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

  const handleLoadExample = useCallback((example: FactorExample) => {
    // Loading an example primes the textarea with the natural-language hypothesis
    // so the user's translate→backtest pipeline runs exactly as it would for
    // their own input. We don't short-circuit straight to /backtest.
    setText(locale === "zh" ? example.hypothesisZh : example.hypothesisEn);
    setResult(null);
    setBacktest(null);
    setError(null);
    setBacktestError(null);
    setActiveId(null);
  }, [locale]);

  // P6.D — hand off the current spec to /backtest via sessionStorage so
  // the user lands on the workstation pre-filled. sessionStorage is
  // route-scoped to the tab, cleared on read so a second navigation
  // doesn't keep re-priming the form.
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
      // sessionStorage disabled — fall through, just navigate; user re-types
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

  const icColor = result
    ? Math.abs(result.smoke.ic_spearman) >= 0.03
      ? "text-accent"
      : "text-muted"
    : "text-muted";

  return (
    <main className="flex h-full flex-col overflow-y-auto p-5">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-4">
          <header>
            <h1 className="text-xl font-semibold text-text">
              {t(locale, "alpha.title")}
            </h1>
            <p className="mt-1 text-sm text-muted">{t(locale, "alpha.subtitle")}</p>
          </header>

          <Card padding="md">
        <div className="flex flex-col gap-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t(locale, "alpha.placeholder")}
            rows={3}
            className="w-full resize-y rounded-md border border-border bg-[var(--toggle-bg)] px-3 py-2 text-base text-text placeholder:text-muted focus:border-accent focus:outline-none"
            disabled={loading}
          />
          <div className="flex flex-wrap items-end gap-3">
            <Select
              label={t(locale, "alpha.universe")}
              value={universe}
              onChange={(v) => setUniverse(v as FactorUniverse)}
              options={UNIVERSES}
              className="w-40"
            />
            <Button
              variant="primary"
              size="md"
              onClick={onSubmit}
              disabled={loading || text.trim().length === 0}
            >
              {loading ? t(locale, "alpha.submitting") : t(locale, "alpha.submit")}
            </Button>
            <p className="ml-auto max-w-xl text-[13px] leading-relaxed text-muted">
              {t(locale, "alpha.tips")}
            </p>
          </div>
          {error ? (
            <p className="text-sm text-red-400">
              {t(locale, "alpha.errorPrefix")}
              {error}
            </p>
          ) : null}
        </div>
      </Card>

      <FactorExamples onLoad={handleLoadExample} />

      {result ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card padding="md" className="lg:col-span-2">
            <header className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-text">
                {t(locale, "alpha.resultSpec")}
              </h2>
              <div className="flex items-center gap-2">
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
                              ? backtest.equity_curve[backtest.equity_curve.length - 1].value /
                                  backtest.equity_curve[0].value -
                                1
                              : undefined,
                          testIc: backtest.test_metrics.ic_spearman,
                        }
                      : undefined
                  }
                />
                <Button variant="ghost" size="sm" onClick={jumpToBacktest}>
                  {t(locale, "alpha.runBacktest")}
                </Button>
              </div>
            </header>
            <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-2 text-sm">
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
          </Card>

          <Card padding="md">
            <h2 className="mb-3 text-base font-semibold text-text">
              {t(locale, "alpha.resultSmoke")}
            </h2>
            <dl className="flex flex-col gap-3 text-sm">
              <KV
                label={t(locale, "alpha.labelIC")}
                value={result.smoke.ic_spearman.toFixed(4)}
                valueClass={`font-mono text-base ${icColor}`}
              />
              <KV
                label={t(locale, "alpha.labelRows")}
                value={result.smoke.rows_valid.toString()}
              />
              <KV
                label={t(locale, "alpha.labelRuntime")}
                value={`${result.smoke.runtime_ms.toFixed(1)} ms`}
              />
              <KV
                label={t(locale, "alpha.labelTokens")}
                value={`${result.llm_tokens.prompt} + ${result.llm_tokens.completion}`}
              />
            </dl>
          </Card>
        </div>
      ) : null}

      {result ? (
        <Card padding="md">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-text">
                {t(locale, "alpha.backtest.title")}
              </h2>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">
                {t(locale, "alpha.backtest.subtitle")}
              </p>
            </div>
            <Button
              variant="primary"
              size="md"
              onClick={onBacktest}
              disabled={backtesting}
            >
              {backtesting
                ? t(locale, "alpha.backtest.running")
                : t(locale, "alpha.backtest.run")}
            </Button>
          </div>

          <div className="mb-3 rounded-md border border-border bg-[var(--card-inner,transparent)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold text-text">
                {t(locale, "alpha.backtest.directionLabel")}
              </span>
              {(["long_only", "long_short", "short_only"] as const).map((dir) => {
                const labelKey =
                  dir === "long_only"
                    ? "alpha.backtest.dirLongOnly"
                    : dir === "long_short"
                      ? "alpha.backtest.dirLongShort"
                      : "alpha.backtest.dirShortOnly";
                const active = direction === dir;
                return (
                  <button
                    key={dir}
                    type="button"
                    onClick={() => setDirection(dir)}
                    className={`rounded-md border px-2.5 py-1 text-[13px] transition ${
                      active
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-border bg-[var(--toggle-bg)] text-text-secondary hover:border-accent hover:text-accent"
                    }`}
                  >
                    {t(locale, labelKey)}
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-[12px] leading-relaxed text-muted">
              {t(locale, DIRECTION_HELP_KEY[direction])}
            </p>
          </div>

          {backtestError ? (
            <p className="mb-2 text-sm text-red-400">
              {t(locale, "alpha.backtest.errorPrefix")}
              {backtestError}
            </p>
          ) : null}

          {backtest ? (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                <MetricTile
                  label={t(locale, "alpha.backtest.trainSharpe")}
                  value={backtest.train_metrics.sharpe.toFixed(2)}
                />
                <MetricTile
                  label={t(locale, "alpha.backtest.testSharpe")}
                  value={backtest.test_metrics.sharpe.toFixed(2)}
                  emphasize={
                    backtest.test_metrics.sharpe >= 1.0
                      ? "pos"
                      : backtest.test_metrics.sharpe <= -1.0
                        ? "neg"
                        : undefined
                  }
                />
                <MetricTile
                  label={t(locale, "alpha.backtest.trainIC")}
                  value={backtest.train_metrics.ic_spearman.toFixed(4)}
                />
                <MetricTile
                  label={t(locale, "alpha.backtest.testIC")}
                  value={backtest.test_metrics.ic_spearman.toFixed(4)}
                />
                <MetricTile
                  label={t(locale, "alpha.backtest.trainReturn")}
                  value={`${(backtest.train_metrics.total_return * 100).toFixed(2)}%`}
                />
                <MetricTile
                  label={t(locale, "alpha.backtest.testReturn")}
                  value={`${(backtest.test_metrics.total_return * 100).toFixed(2)}%`}
                />
              </div>
              <FactorPnLChart data={backtest} />
            </div>
          ) : null}
        </Card>
      ) : null}
        </div>

        <aside className="lg:sticky lg:top-5 lg:self-start">
          <HypothesisHistoryPanel
            favorites={favorites}
            recent={recent}
            activeId={activeId}
            onLoad={handleLoadEntry}
            onToggleFavorite={handleToggleFavorite}
            onRemove={handleRemove}
          />
        </aside>
      </div>
    </main>
  );
}

function MetricTile({
  label,
  value,
  emphasize,
}: {
  readonly label: string;
  readonly value: string;
  readonly emphasize?: "pos" | "neg";
}) {
  const color =
    emphasize === "pos"
      ? "text-accent"
      : emphasize === "neg"
        ? "text-red-400"
        : "text-text";
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border bg-[var(--card-inner,transparent)] px-3 py-2">
      <span className="text-[12px] uppercase tracking-wide text-muted">
        {label}
      </span>
      <span className={`font-mono text-base ${color}`}>{value}</span>
    </div>
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
      <dt className="text-muted">{label}</dt>
      <dd className={mono ? "break-all font-mono text-text" : "text-text"}>
        {value}
      </dd>
    </>
  );
}

function KV({
  label,
  value,
  valueClass,
}: {
  readonly label: string;
  readonly value: string;
  readonly valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{label}</span>
      <span className={valueClass ?? "font-mono text-text"}>{value}</span>
    </div>
  );
}
