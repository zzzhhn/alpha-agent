"use client";

import { FlaskConical, Loader2, ShieldCheck } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";

export function BacktestEmptyState({ running }: { readonly running: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <section className="border-b border-tm-rule px-6 py-4">
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(300px,1fr)] gap-4">
        <section className="min-h-[330px] border border-tm-rule bg-tm-bg" aria-label={zh ? "净值与基准" : "Equity and benchmark"}>
          <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4">
            <span className="font-tm-mono text-[11px] font-semibold tracking-[0.08em] text-tm-fg">
              {zh ? "净值、基准与回撤" : "Equity, benchmark, and drawdown"}
            </span>
            <span className="font-tm-mono text-[9px] text-tm-muted">IS / OOS</span>
          </div>
          <div className="relative flex h-[286px] items-center justify-center overflow-hidden px-8 text-center">
            <div className="pointer-events-none absolute inset-6 bg-[linear-gradient(to_right,var(--tm-rule)_1px,transparent_1px),linear-gradient(to_bottom,var(--tm-rule)_1px,transparent_1px)] bg-[size:20%_25%] opacity-55" />
            <div className="relative max-w-md bg-tm-bg/90 px-5 py-4">
              {running ? (
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-tm-accent" />
              ) : (
                <FlaskConical className="mx-auto h-5 w-5 text-tm-muted" />
              )}
              <h2 className="mt-3 text-[12px] font-semibold text-tm-fg">
                {running ? (zh ? "正在建立验证证据" : "Building validation evidence") : (zh ? "运行后在同一坐标系比较策略与基准" : "Run to compare strategy and benchmark on one scale")}
              </h2>
              <p className="mt-2 text-[9.5px] leading-5 text-tm-muted">
                {running
                  ? (zh ? "结果到达前保留工作台结构，避免页面跳动。" : "The workbench keeps its geometry while results arrive.")
                  : (zh ? "先确认表达式、方向和成本。系统不会用示例曲线冒充真实结果。" : "Confirm expression, direction, and cost. Sample curves never impersonate real results.")}
              </p>
            </div>
          </div>
        </section>

        <section className="border border-tm-rule bg-tm-bg">
          <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4">
            <span className="font-tm-mono text-[11px] font-semibold tracking-[0.08em] text-tm-fg">
              {zh ? "验证门槛" : "Validation gates"}
            </span>
            <span className="text-[9px] text-tm-muted">{running ? (zh ? "计算中" : "Running") : (zh ? "等待运行" : "Waiting")}</span>
          </div>
          <div className="divide-y divide-tm-rule">
            {[
              zh ? "样本外 Sharpe" : "OOS Sharpe",
              zh ? "最大回撤" : "Max drawdown",
              zh ? "样本外 IC" : "OOS IC",
              zh ? "换手与成本" : "Turnover and cost",
              zh ? "集中度" : "Concentration",
              zh ? "泄漏检查" : "Leakage check",
            ].map((label) => (
              <div key={label} className="grid min-h-[42px] grid-cols-[24px_1fr_auto] items-center gap-3 px-4 text-[10px]">
                <ShieldCheck className={`h-3.5 w-3.5 ${running ? "animate-pulse text-tm-accent" : "text-tm-muted"}`} />
                <span className="text-tm-fg-2">{label}</span>
                <span className="font-mono text-tm-muted">—</span>
              </div>
            ))}
          </div>
          <p className="border-t border-tm-rule px-4 py-2 text-[9px] leading-4 text-tm-muted">
            {zh ? "只显示服务端能够验证的门槛，缺失项保持未知。" : "Only server-verifiable gates are scored; missing evidence stays unknown."}
          </p>
        </section>
      </div>

      <div className="mt-3 grid grid-cols-[140px_repeat(3,minmax(0,1fr))] gap-2">
        <div className="flex items-center border border-tm-rule bg-tm-bg-2 px-4 text-[10px] font-semibold text-tm-fg-2">{zh ? "对比摘要" : "Comparison"}</div>
        {[zh ? "本次运行" : "Current", zh ? "固定基线" : "Baseline", zh ? "上次运行" : "Previous"].map((label) => (
          <div key={label} className="border border-tm-rule bg-tm-bg px-4 py-3">
            <p className="text-[9px] uppercase tracking-[0.08em] text-tm-muted">{label}</p>
            <p className="mt-2 font-mono text-[10px] text-tm-muted">Sharpe — · MaxDD — · IC —</p>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-1.5" aria-label={zh ? "诊断摘要" : "Diagnostic summaries"}>
        {[
          [zh ? "风险明细" : "Risk detail", "3"],
          [zh ? "市场状态拆分" : "Regime breakdown", "2"],
          [zh ? "当前持仓" : "Holdings", "2"],
          [zh ? "执行与成本" : "Operations", "2"],
        ].map(([label, count]) => (
          <div key={label} className="flex min-h-8 items-center justify-between border border-tm-rule bg-tm-bg px-3 font-tm-mono text-[9.5px]">
            <span className="text-tm-accent">› {label}</span>
            <span className="text-tm-muted">{count} {zh ? "项 · 运行后可展开" : "items · available after run"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
