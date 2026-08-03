"use client";

import { BarChart3, FlaskConical, ShieldCheck } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";

export function BacktestEmptyState({ running }: { readonly running: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <section className="border border-tm-rule bg-tm-bg-2/30 px-5 py-8">
      <div className="mx-auto max-w-3xl text-center">
        <FlaskConical className={`mx-auto h-6 w-6 ${running ? "animate-pulse text-tm-accent" : "text-tm-muted"}`} />
        <h2 className="mt-3 text-[13px] font-semibold">
          {running ? (zh ? "正在建立验证证据" : "Building validation evidence") : (zh ? "用一次回测回答一个可反驳的问题" : "Use one backtest to answer one falsifiable question")}
        </h2>
        <p className="mt-2 text-[10px] leading-5 text-tm-muted">
          {running
            ? (zh ? "完成后只会先展示净值路径、回撤、Walk-forward 和五项验证门槛。" : "The first result will focus on equity, drawdown, walk-forward evidence, and five validation gates.")
            : (zh ? "确认表达式、方向和成本后运行。完整风险、市场状态、持仓和运营明细会按需出现。" : "Confirm expression, direction, and cost, then run. Detailed risk, regime, holdings, and operations appear on demand.")}
        </p>
        <div className="mt-5 grid grid-cols-3 gap-px border border-tm-rule bg-tm-rule text-left text-[9.5px]">
          <div className="bg-tm-bg px-3 py-3"><BarChart3 className="h-3.5 w-3.5 text-tm-accent" /><p className="mt-2 text-tm-fg">{zh ? "先看收益路径与基准" : "Start with path and benchmark"}</p></div>
          <div className="bg-tm-bg px-3 py-3"><ShieldCheck className="h-3.5 w-3.5 text-tm-accent" /><p className="mt-2 text-tm-fg">{zh ? "再找足以否定的证据" : "Then seek disconfirming evidence"}</p></div>
          <div className="bg-tm-bg px-3 py-3"><FlaskConical className="h-3.5 w-3.5 text-tm-accent" /><p className="mt-2 text-tm-fg">{zh ? "最后与基线和上次比较" : "Finally compare baseline and prior"}</p></div>
        </div>
      </div>
    </section>
  );
}
