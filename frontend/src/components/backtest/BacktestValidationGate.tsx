"use client";

import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";
import { evaluateBacktestGates, type BacktestGateThresholds } from "@/lib/backtest-gates";
import type { Run } from "./types";

const LABELS = {
  sharpe: { zh: "风险调整收益", en: "Sharpe" },
  maxDD: { zh: "最大回撤", en: "Max drawdown" },
  ic: { zh: "样本外 IC", en: "OOS IC" },
  turnover: { zh: "换手率", en: "Turnover" },
  annReturn: { zh: "年化收益", en: "Annual return" },
};

function format(key: keyof typeof LABELS, value: number | null): string {
  if (value === null) return "—";
  if (key === "sharpe") return value.toFixed(2);
  if (key === "ic") return value.toFixed(4);
  return `${(value * 100).toFixed(1)}%`;
}

export function BacktestValidationGate({
  currentRun,
  thresholds,
}: {
  readonly currentRun: Run | null;
  readonly thresholds: BacktestGateThresholds;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const gates = currentRun ? evaluateBacktestGates(currentRun.metrics, thresholds) : [];
  const failed = gates.filter((gate) => gate.status === "fail").length;

  return (
    <section className="h-full border border-tm-rule bg-tm-bg">
      <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4">
        <span className="text-[12px] font-semibold tracking-[0.08em] text-tm-fg">
          {zh ? "验证门槛" : "Validation gates"}
        </span>
        <span className={`text-[10px] ${failed > 0 ? "text-tm-neg" : gates.length > 0 ? "text-tm-pos" : "text-tm-muted"}`}>
          {gates.length === 0 ? (zh ? "等待运行" : "Waiting") : failed > 0 ? (zh ? `${failed} 项反证` : `${failed} counter-evidence`) : (zh ? "全部通过" : "All pass")}
        </span>
      </div>
      {gates.length === 0 ? (
        <div className="flex min-h-52 items-center justify-center px-4 text-center text-[10px] leading-5 text-tm-muted">
          {zh ? "运行回测后，这里会同时显示原值、门槛和是否形成反证。" : "Run a backtest to see each raw value, threshold, and counter-evidence status."}
        </div>
      ) : (
        <div className="divide-y divide-tm-rule">
          {gates.map((gate) => {
            const label = LABELS[gate.key];
            const Icon = gate.status === "pass" ? CheckCircle2 : gate.status === "fail" ? XCircle : HelpCircle;
            const tone = gate.status === "pass" ? "text-tm-pos" : gate.status === "fail" ? "text-tm-neg" : "text-tm-muted";
            const comparator = gate.lowerIsBetter ? "≤" : "≥";
            return (
              <div key={gate.key} className="grid min-h-[58px] grid-cols-[28px_minmax(140px,1fr)_80px_92px] items-center gap-3 px-4 py-2 text-[10.5px]">
                <span className={`flex h-6 w-6 items-center justify-center border ${gate.status === "pass" ? "border-tm-pos/50" : gate.status === "fail" ? "border-tm-neg/50" : "border-tm-rule"}`}>
                  <Icon className={`h-3.5 w-3.5 ${tone}`} />
                </span>
                <div>
                  <p className="text-tm-fg">{zh ? label.zh : label.en}</p>
                  <p className="mt-1 text-[9px] text-tm-muted">{gate.lowerIsBetter ? (zh ? "越低越好" : "Lower is better") : (zh ? "越高越好" : "Higher is better")}</p>
                </div>
                <span className={`text-right font-mono text-[12px] ${tone}`}>{format(gate.key, gate.value)}</span>
                <span className="text-right font-mono text-tm-muted">{comparator} {format(gate.key, gate.threshold)}</span>
              </div>
            );
          })}
        </div>
      )}
      <p className="border-t border-tm-rule px-3 py-2 text-[9px] leading-4 text-tm-muted">
        {zh ? "门槛分别判定，不用综合分掩盖回撤、换手或负 IC。" : "Gates remain separate so a composite score cannot hide drawdown, turnover, or negative IC."}
      </p>
    </section>
  );
}
