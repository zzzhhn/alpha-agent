"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { FactorBacktestResponse } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: FactorBacktestResponse | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-3 w-1/2 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-20 w-full animate-pulse rounded bg-tm-bg-3" />
      <div className="h-3 w-3/4 animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}

export function BacktestPane({ state, data, errorMessage, onRetry }: Props) {
  const { locale } = useLocale();

  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="font-tm-mono text-xs font-semibold uppercase text-tm-fg-2">
        {t(locale, "alpha.pane.backtest" as Parameters<typeof t>[1])}
      </h3>
      {state === "waiting" || state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="flex flex-col gap-2 text-xs text-tm-neg">
          <div className="break-words font-tm-mono">{errorMessage}</div>
          {onRetry ? (
            <button
              onClick={onRetry}
              className="w-fit rounded border border-tm-neg/40 px-2 py-0.5 font-tm-mono text-tm-neg hover:bg-tm-neg/10"
            >
              {t(locale, "alpha.pane.retryBacktest" as Parameters<typeof t>[1])}
            </button>
          ) : null}
        </div>
      ) : data ? (
        <>
          <div className="font-tm-mono text-sm font-semibold text-tm-fg">
            Sharpe = <span className="font-mono">{data.test_metrics.sharpe.toFixed(2)}</span>
          </div>
          <div className="font-tm-mono text-[11px] text-tm-muted">
            maxDD ={" "}
            <span className="font-mono">
              {data.test_metrics.max_drawdown !== undefined
                ? `${(data.test_metrics.max_drawdown * 100).toFixed(0)}%`
                : "n/a"}
            </span>
            {" "}&bull;{" "}
            IC = <span className="font-mono">{data.test_metrics.ic_spearman.toFixed(4)}</span>
          </div>
        </>
      ) : null}
    </section>
  );
}
