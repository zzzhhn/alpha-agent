"use client";

import { AlertCircle, Check, Loader2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ChainState, ThresholdEval, VerdictMetrics } from "./types";

interface Props {
  state: ChainState;
  metrics: VerdictMetrics;
  thresholds: ThresholdEval;
  canSave: boolean;
  onSave: () => void;
  onReTranslate: () => void;
}

const MARK = {
  ok: <span className="ml-1 text-tm-pos">&#10003;</span>,
  warn: <span className="ml-1 text-tm-warn">&#9888;</span>,
  bad: <span className="ml-1 text-tm-neg">&#10007;</span>,
};

export function VerdictBar({ state, metrics, thresholds, canSave, onSave, onReTranslate }: Props) {
  const { locale } = useLocale();

  if (state.kind === "idle") {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm text-tm-muted">
        {t(locale, "alpha.verdict.idle" as Parameters<typeof t>[1])}
      </section>
    );
  }

  if (state.kind === "translate_error") {
    return (
      <section className="flex items-center justify-between rounded border border-tm-neg/40 bg-tm-neg/10 px-4 py-3">
        <div className="flex items-center gap-2 font-tm-mono text-sm text-tm-neg">
          <AlertCircle className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          <span>
            {t(locale, "alpha.verdict.translateFailed" as Parameters<typeof t>[1])}
            {state.message}
          </span>
        </div>
        <button
          onClick={onReTranslate}
          className="rounded border border-tm-neg/60 px-3 py-1 font-tm-mono text-xs font-semibold text-tm-neg hover:bg-tm-neg/20"
        >
          {t(locale, "alpha.verdict.retranslate" as Parameters<typeof t>[1])}
        </button>
      </section>
    );
  }

  const loading = state.kind === "translating" || state.kind === "backtesting";
  const stageText =
    state.kind === "translating"
      ? t(locale, "alpha.verdict.translating" as Parameters<typeof t>[1])
      : state.kind === "backtesting"
      ? t(locale, "alpha.verdict.backtesting" as Parameters<typeof t>[1])
      : null;

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded border border-tm-rule bg-tm-bg-2 px-4 py-3 font-tm-mono text-sm">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        {loading && (
          <span className="flex items-center gap-1.5 text-tm-fg-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {stageText}
          </span>
        )}
        {metrics.ic !== null && (
          <span
            title={thresholds.ic?.threshold ?? t(locale, "alpha.verdict.icThreshold" as Parameters<typeof t>[1])}
            className="cursor-help text-tm-fg"
          >
            IC={metrics.ic.toFixed(4)}
            {thresholds.ic && MARK[thresholds.ic.status]}
          </span>
        )}
        {metrics.sharpe !== null && (
          <span
            title={thresholds.sharpe?.threshold ?? t(locale, "alpha.verdict.sharpeThreshold" as Parameters<typeof t>[1])}
            className="cursor-help text-tm-fg"
          >
            Sharpe={metrics.sharpe.toFixed(2)}
            {thresholds.sharpe && MARK[thresholds.sharpe.status]}
          </span>
        )}
        {metrics.maxDrawdown !== null && (
          <span
            title={thresholds.maxDrawdown?.threshold ?? t(locale, "alpha.verdict.maxDdThreshold" as Parameters<typeof t>[1])}
            className="cursor-help text-tm-fg"
          >
            maxDD={(metrics.maxDrawdown * 100).toFixed(0)}%
            {thresholds.maxDrawdown && MARK[thresholds.maxDrawdown.status]}
          </span>
        )}
        {state.kind === "backtest_error" && (
          <span className="text-tm-warn">
            {t(locale, "alpha.backtest.errorPrefix" as Parameters<typeof t>[1])}
            {state.message.slice(0, 80)}
          </span>
        )}
      </div>
      {canSave && (
        <button
          onClick={onSave}
          aria-label={t(locale, "alpha.verdict.saveToZoo" as Parameters<typeof t>[1])}
          className="inline-flex items-center gap-1 rounded bg-tm-accent px-3 py-1.5 font-tm-mono text-sm font-semibold text-tm-bg hover:opacity-90"
        >
          <Check className="h-3.5 w-3.5" strokeWidth={1.75} />
          {t(locale, "alpha.verdict.saveToZoo" as Parameters<typeof t>[1])}
        </button>
      )}
    </section>
  );
}
