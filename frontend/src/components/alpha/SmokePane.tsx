"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
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
  const { locale } = useLocale();

  return (
    <section className="flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 p-3">
      <h3 className="font-tm-mono text-xs font-semibold uppercase text-tm-fg-2">
        {t(locale, "alpha.pane.smoke" as Parameters<typeof t>[1])}
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
              {t(locale, "alpha.pane.retry" as Parameters<typeof t>[1])}
            </button>
          ) : null}
        </div>
      ) : data ? (
        <>
          <div className="font-tm-mono text-sm font-semibold text-tm-fg">
            IC = <span className="font-mono">{data.ic_spearman.toFixed(4)}</span>
          </div>
          {data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {t(locale, "alpha.degenerateBlocked" as Parameters<typeof t>[1])}
            </div>
          ) : null}
          {/* Advisory (not blocking): a change/reversal expression churns its
              whole book and is punished by transaction costs. Shown alongside
              degenerate; a factor can in principle trip neither, one, or both. */}
          {data.high_turnover && !data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {t(locale, "alpha.highTurnoverWarn" as Parameters<typeof t>[1])}
            </div>
          ) : null}
          {/* Advisory (not blocking): factor ranking collapses under small input
              noise — likely overfit. Independent of turnover (a factor can be
              fragile without churning), so shown separately. */}
          {data.low_robustness && !data.degenerate ? (
            <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-2 py-1 font-tm-mono text-[11px] text-tm-warn">
              {t(locale, "alpha.lowRobustnessWarn" as Parameters<typeof t>[1])}
            </div>
          ) : null}
          <div className="font-tm-mono text-[11px] text-tm-muted">
            {t(locale, "alpha.pane.rowsValid" as Parameters<typeof t>[1])}=<span className="font-mono">{data.rows_valid}</span>
            {" "}&bull;{" "}
            {t(locale, "alpha.pane.runtime" as Parameters<typeof t>[1])}=<span className="font-mono">{data.runtime_ms}ms</span>
            {data.factor_std !== undefined
              ? <> &bull; {t(locale, "alpha.pane.std" as Parameters<typeof t>[1])}=<span className="font-mono">{data.factor_std.toFixed(4)}</span></>
              : null}
            {data.turnover !== undefined
              ? <> &bull; {t(locale, "alpha.pane.turnover" as Parameters<typeof t>[1])}=<span className={`font-mono ${data.high_turnover ? "text-tm-warn" : ""}`}>{(data.turnover * 100).toFixed(0)}%</span></>
              : null}
            {data.robustness !== undefined
              ? <> &bull; {t(locale, "alpha.pane.robustness" as Parameters<typeof t>[1])}=<span className={`font-mono ${data.low_robustness ? "text-tm-warn" : ""}`}>{data.robustness.toFixed(2)}</span></>
              : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
