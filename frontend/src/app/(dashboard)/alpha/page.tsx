"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
import { FactorPnLChart } from "@/components/charts/FactorPnLChart";
import type {
  FactorBacktestResponse,
  FactorUniverse,
  HypothesisTranslateResponse,
} from "@/lib/types";

const UNIVERSES: readonly { value: FactorUniverse; label: string }[] = [
  { value: "CSI300", label: "CSI300" },
  { value: "CSI500", label: "CSI500" },
  { value: "SP500", label: "S&P500" },
  { value: "custom", label: "Custom" },
];

export default function AlphaPage() {
  const { locale } = useLocale();
  const [text, setText] = useState("");
  const [universe, setUniverse] = useState<FactorUniverse>("CSI500");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HypothesisTranslateResponse | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<FactorBacktestResponse | null>(null);

  async function onSubmit() {
    if (text.trim().length === 0) return;
    setLoading(true);
    setError(null);
    const response = await translateHypothesis({
      text: text.trim(),
      universe,
    });
    setLoading(false);
    if (response.error) {
      setError(response.error);
      setResult(null);
      return;
    }
    setResult(response.data);
    // A new spec invalidates the previous backtest result.
    setBacktest(null);
    setBacktestError(null);
  }

  async function onBacktest() {
    if (!result) return;
    setBacktesting(true);
    setBacktestError(null);
    const response = await runFactorBacktest({ spec: result.spec });
    setBacktesting(false);
    if (response.error) {
      setBacktestError(response.error);
      setBacktest(null);
      return;
    }
    setBacktest(response.data);
  }

  const icColor = result
    ? Math.abs(result.smoke.ic_spearman) >= 0.03
      ? "text-accent"
      : "text-muted"
    : "text-muted";

  return (
    <main className="flex h-full flex-col gap-4 overflow-y-auto p-5">
      <header>
        <h1 className="text-lg font-semibold text-text">
          {t(locale, "alpha.title")}
        </h1>
        <p className="mt-1 text-xs text-muted">{t(locale, "alpha.subtitle")}</p>
      </header>

      <Card padding="md">
        <div className="flex flex-col gap-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t(locale, "alpha.placeholder")}
            rows={3}
            className="w-full resize-y rounded-md border border-border bg-[var(--toggle-bg)] px-3 py-2 text-sm text-text placeholder:text-muted focus:border-accent focus:outline-none"
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
            <p className="ml-auto max-w-xl text-[11px] leading-relaxed text-muted">
              {t(locale, "alpha.tips")}
            </p>
          </div>
          {error ? (
            <p className="text-xs text-red-400">
              {t(locale, "alpha.errorPrefix")}
              {error}
            </p>
          ) : null}
        </div>
      </Card>

      {result ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card padding="md" className="lg:col-span-2">
            <h2 className="mb-3 text-sm font-semibold text-text">
              {t(locale, "alpha.resultSpec")}
            </h2>
            <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-2 text-xs">
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
            <h2 className="mb-3 text-sm font-semibold text-text">
              {t(locale, "alpha.resultSmoke")}
            </h2>
            <dl className="flex flex-col gap-3 text-xs">
              <KV
                label={t(locale, "alpha.labelIC")}
                value={result.smoke.ic_spearman.toFixed(4)}
                valueClass={`font-mono text-sm ${icColor}`}
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
              <h2 className="text-sm font-semibold text-text">
                {t(locale, "alpha.backtest.title")}
              </h2>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">
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

          {backtestError ? (
            <p className="mb-2 text-xs text-red-400">
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
      <span className="text-[10px] uppercase tracking-wide text-muted">
        {label}
      </span>
      <span className={`font-mono text-sm ${color}`}>{value}</span>
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
