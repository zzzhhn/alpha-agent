"use client";

import { FlaskConical, Loader2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";

export function BacktestEmptyState({ running }: { readonly running: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const questions = zh
    ? ["样本外表现", "Walk-forward 稳定性", "交易成本韧性", "持仓集中度", "前视与数据风险"]
    : ["Out-of-sample performance", "Walk-forward stability", "Transaction-cost robustness", "Concentration check", "Look-ahead and data risk"];
  return (
    <section className="border-b border-tm-rule px-6 py-4" aria-busy={running}>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.8fr)_minmax(360px,1fr)]">
        <section className="flex min-w-0 flex-col border border-tm-rule bg-tm-bg-2" aria-label={zh ? "净值与基准" : "Equity and benchmark"}>
          <div className="flex items-center justify-between gap-3 border-b border-tm-rule px-4 py-3">
            <span className="font-tm-mono text-xs font-semibold text-tm-fg">{zh ? "净值、基准与回撤" : "Equity, benchmark, and drawdown"}</span>
            <span className="font-tm-mono text-xs text-tm-muted">IS / OOS</span>
          </div>
          <div className="flex min-h-[190px] flex-1 items-center gap-5 px-6 py-6">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center border border-tm-rule text-tm-accent">
              {running ? <Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" /> : <FlaskConical className="h-5 w-5" />}
            </div>
            <div className="max-w-lg">
              <h2 className="text-[18px] font-semibold leading-6 text-tm-fg">{running ? (zh ? "正在构建验证证据" : "Building validation evidence") : (zh ? "策略是否经得起检验？" : "Does the strategy hold up?")}</h2>
              <p className="mt-2 text-xs leading-5 text-tm-muted">{running ? (zh ? "回测完成后显示实际净值与风险，不预填结果。" : "Actual equity and risk appear when the run completes.") : (zh ? "在同一坐标系对照策略与基准，并区分样本内和样本外。运行后显示实际结果。" : "Compare strategy and benchmark on one scale, with in-sample and out-of-sample evidence kept distinct.")}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-tm-rule px-4 py-2 font-tm-mono text-xs text-tm-muted"><span>{zh ? "策略净值" : "Strategy equity"}</span><span>{zh ? "基准对照" : "Benchmark"}</span><span>{zh ? "回撤路径" : "Drawdown"}</span></div>
        </section>
        <section className="border border-tm-rule bg-tm-bg" aria-label={zh ? "验证门槛" : "Validation gates"}>
          <div className="flex items-center justify-between border-b border-tm-rule px-4 py-3"><span className="text-xs font-semibold text-tm-fg">{zh ? "验证门槛" : "Validation gates"}</span><span className="text-xs text-tm-muted">{running ? (zh ? "计算中" : "Running") : (zh ? "尚未评估" : "Not evaluated")}</span></div>
          <div className="divide-y divide-tm-rule">{questions.map((label, index) => <div key={label} className="flex items-center gap-3 px-4 py-2 text-xs"><span className="font-tm-mono tabular-nums text-tm-muted">0{index + 1}</span><span className="flex-1 text-tm-fg-2">{label}</span><span className="text-tm-muted">—</span></div>)}</div>
          <p className="border-t border-tm-rule px-4 py-2 text-xs text-tm-muted">{zh ? "未评估与已通过不同，缺失证据保留为空。" : "Not evaluated is not a pass. Missing evidence stays empty."}</p>
        </section>
      </div>
    </section>
  );
}
