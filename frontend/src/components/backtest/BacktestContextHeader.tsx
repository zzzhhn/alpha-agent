"use client";

import { Cpu, Gauge } from "lucide-react";

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
      title={<>{zh ? "回测" : "Backtest"} <span className="font-normal text-tm-fg-2">Backtest</span></>}
      subtitle={zh ? "反驳、比较并保留可信策略" : "Refute, compare, and retain credible strategies"}
      statuses={[
        { label: zh ? "计算模式" : "Compute mode", value: params.mode === "walk_forward" ? "WALK-FORWARD" : "STATIC" },
        { label: zh ? "容量保护" : "Capacity guard", value: zh ? "单实例 1 项" : "1 job / instance", tone: running ? "warning" : "positive" },
        { label: zh ? "队列状态" : "Queue", value: running ? (zh ? "运行中" : "RUNNING") : (zh ? "空闲" : "IDLE"), tone: running ? "warning" : "positive" },
        { label: zh ? "最近运行" : "Last run", value: lastRun },
      ]}
      action={(
        <div className="flex items-center gap-3 border border-tm-rule px-3 py-2 text-xs text-tm-muted">
          <Cpu className="h-3.5 w-3.5 text-tm-accent" />
          <span>{zh ? "繁重计算由服务线程执行" : "Heavy compute runs off the request loop"}</span>
          <Gauge className="h-3.5 w-3.5" />
        </div>
      )}
    />
  );
}
