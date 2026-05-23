"use client";

import type { SmokeReport } from "@/lib/types";
import type { PaneState } from "./types";

interface Props {
  state: PaneState;
  data: SmokeReport | null;
  errorMessage: string | null;
  onRetry?: () => void;
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-3 w-2/3 animate-pulse rounded bg-tm-bg-3" />
      <div className="h-12 w-full animate-pulse rounded bg-tm-bg-3" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-tm-bg-3" />
    </div>
  );
}

export function SmokePane({ state, data, errorMessage, onRetry }: Props) {
  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="text-xs font-semibold uppercase text-tm-fg-2">SMOKE PROBE</h3>
      {state === "waiting" || state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="flex flex-col gap-2 text-xs text-tm-neg">
          <div className="break-words">{errorMessage}</div>
          {onRetry ? (
            <button
              onClick={onRetry}
              className="w-fit rounded border border-tm-neg/40 px-2 py-0.5 text-tm-neg hover:bg-tm-neg/10"
            >
              Retry
            </button>
          ) : null}
        </div>
      ) : data ? (
        <>
          <div className="text-sm font-semibold text-tm-fg">
            IC = {data.ic_spearman.toFixed(4)}
          </div>
          {data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 text-[11px] text-tm-warn">
              Degenerate factor: cross-section variance near zero. Backtest unreliable.
            </div>
          ) : null}
          <div className="text-[11px] text-tm-muted">
            rows_valid={data.rows_valid} &bull; runtime={data.runtime_ms}ms
            {data.factor_std !== undefined ? ` • std=${data.factor_std.toFixed(4)}` : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
