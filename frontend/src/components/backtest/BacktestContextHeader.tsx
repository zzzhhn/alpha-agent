"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import type { BacktestParams, Run, RunState } from "./types";

export function BacktestContextHeader({
  params,
  runState,
  currentRun,
}: {
  readonly params: BacktestParams;
  readonly runState: RunState;
  readonly currentRun: Run | null;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const running = runState.kind === "running";
  const lastRun = currentRun
    ? new Date(currentRun.ts).toLocaleTimeString(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" })
    : (zh ? "尚未运行" : "Not run");

  return (
    <WorkbenchHeader
      eyebrow={zh ? "研究工作台" : "Research workbench"}
      title={zh ? <>回测 <span className="font-normal text-tm-fg-2">Backtest</span></> : "Backtest"}
      subtitle={zh ? "反驳、比较并保留可信策略" : "Refute, compare, and retain credible strategies"}
      statuses={[
        { label: zh ? "验证模式" : "Validation mode", value: params.mode === "walk_forward" ? "Walk-forward" : (zh ? "固定样本" : "Static split") },
        { label: zh ? "计算状态" : "Compute", value: running ? (zh ? "运行中 · 单任务" : "Running · 1 job") : (zh ? "就绪" : "Ready"), tone: running ? "warning" : "default" },
        { label: zh ? "最近运行" : "Last run", value: lastRun },
      ]}
    />
  );
}
