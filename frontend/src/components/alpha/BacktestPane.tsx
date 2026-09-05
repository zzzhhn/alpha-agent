"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { FactorBacktestResponse } from "@/lib/types";
import { TmButton } from "@/components/tm/TmButton";
import { PanePlaceholder } from "./PanePlaceholder";
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
      <div className="h-3 w-1/2 animate-pulse rounded-[2px] bg-tm-bg-3" />
      <div className="h-20 w-full animate-pulse rounded-[2px] bg-tm-bg-3" />
      <div className="h-3 w-3/4 animate-pulse rounded-[2px] bg-tm-bg-3" />
    </div>
  );
}

export function BacktestPane({ state, data, errorMessage, onRetry }: Props) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const metrics = data?.test_metrics;
  const gates = data ? [
    { label: "Sharpe", value: metrics?.sharpe.toFixed(2) ?? "—", pass: (metrics?.sharpe ?? -Infinity) >= 1, hint: ">= 1.00" },
    { label: "IC", value: metrics?.ic_spearman.toFixed(4) ?? "—", pass: (metrics?.ic_spearman ?? -Infinity) >= 0.02, hint: ">= 0.02" },
    { label: "MaxDD", value: metrics?.max_drawdown == null ? "—" : `${(metrics.max_drawdown * 100).toFixed(1)}%`, pass: (metrics?.max_drawdown ?? -Infinity) >= -0.15, hint: ">= -15%" },
    { label: zh ? "换手率" : "Turnover", value: metrics?.turnover == null ? "—" : `${(metrics.turnover * 100).toFixed(0)}%`, pass: (metrics?.turnover ?? Infinity) <= 0.5, hint: "<= 50%" },
  ] : [];
  const failedGates = gates.filter((gate) => !gate.pass).length;

  return (
    <section className="flex min-h-[260px] flex-col gap-3 border border-tm-rule bg-tm-bg-2 p-4">
      <h3 className="font-tm-mono text-xs font-semibold uppercase tracking-[0.08em] text-tm-accent">
        {t(locale, "alpha.pane.backtest" as Parameters<typeof t>[1])}
      </h3>
      {state === "waiting" ? (
        <PanePlaceholder
          hint={t(locale, "alpha.pane.waitingBacktest" as Parameters<typeof t>[1])}
        />
      ) : state === "loading" ? (
        <Skeleton />
      ) : state === "error" ? (
        <div className="flex flex-col gap-2 text-xs text-tm-neg">
          <div className="break-words font-tm-mono">{errorMessage}</div>
          {onRetry ? (
            <TmButton
              variant="danger"
              size="xs"
              onClick={onRetry}
              className="w-fit"
            >
              {t(locale, "alpha.pane.retryBacktest" as Parameters<typeof t>[1])}
            </TmButton>
          ) : null}
        </div>
      ) : data ? (
        <>
          <div className={`border-l-2 px-3 py-2 ${failedGates > 0 ? "border-tm-warn bg-tm-warn/5" : "border-tm-pos bg-tm-pos/5"}`}>
            <p className={`text-sm font-semibold ${failedGates > 0 ? "text-tm-warn" : "text-tm-pos"}`}>
              {failedGates > 0 ? (zh ? `${failedGates} 项门槛需要反证` : `${failedGates} gates need counter-evidence`) : (zh ? "关键门槛通过" : "Key gates pass")}
            </p>
            <p className="mt-1 text-xs text-tm-muted">{zh ? "判决使用样本外区间，不以综合分掩盖失败项。" : "Verdict uses OOS evidence and never hides a failed gate in a composite score."}</p>
          </div>
          <div className="divide-y divide-tm-rule border-y border-tm-rule">
            {gates.map((gate) => (
              <div key={gate.label} className="grid min-h-9 grid-cols-[1fr_70px_70px_62px] items-center gap-2 text-xs">
                <span className="text-tm-fg-2">{gate.label}</span>
                <span className="font-mono text-tm-fg">{gate.value}</span>
                <span className="font-mono text-xs text-tm-muted">{gate.hint}</span>
                <span className={gate.pass ? "text-tm-pos" : "text-tm-warn"}>{gate.pass ? (zh ? "通过" : "PASS") : (zh ? "复核" : "REVIEW")}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-px border border-tm-rule bg-tm-rule text-xs">
            <div className="bg-tm-bg px-2 py-2"><p className="text-tm-muted">OOS decay</p><p className="mt-1 font-mono text-tm-fg">{data.oos_decay == null ? "—" : `${(data.oos_decay * 100).toFixed(0)}%`}</p></div>
            <div className="bg-tm-bg px-2 py-2"><p className="text-tm-muted">{zh ? "过拟合标记" : "Overfit flag"}</p><p className={`mt-1 ${data.overfit_flag ? "text-tm-warn" : "text-tm-pos"}`}>{data.overfit_flag ? (zh ? "需要复核" : "REVIEW") : (zh ? "未触发" : "CLEAR")}</p></div>
          </div>
          <div className="mt-auto border-t border-tm-rule pt-2 text-xs leading-5 text-tm-muted">
            <p className="text-tm-accent">{zh ? "下一步建议" : "Next step"}</p>
            <p>{failedGates > 0 ? (zh ? "先修改表达式或降低组合集中度，再进入候选库。" : "Revise the expression or reduce concentration before saving.") : (zh ? "固定候选，并在回测页与基线和上次运行同屏比较。" : "Pin the candidate, then compare it with the baseline and previous run.")}</p>
          </div>
        </>
      ) : null}
    </section>
  );
}
