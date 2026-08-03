"use client";

import { ArrowRight } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import type { FactorUniverse } from "@/lib/types";
import type { ChainState } from "./types";

function translated(state: ChainState) {
  return state.kind === "backtesting" || state.kind === "backtest_error" || state.kind === "done"
    ? state.translate
    : null;
}

export function AlphaResearchContext({
  state,
  universe,
  onOpenBacktest,
}: {
  readonly state: ChainState;
  readonly universe: FactorUniverse;
  readonly onOpenBacktest: () => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const result = translated(state);
  const stage = {
    idle: zh ? "等待假设" : "Awaiting hypothesis",
    translating: zh ? "生成可检验表达式" : "Translating to a testable expression",
    backtesting: zh ? "验证样本外证据" : "Validating out-of-sample evidence",
    done: zh ? "验证完成" : "Validation complete",
    translate_error: zh ? "表达式阶段需恢复" : "Translation needs recovery",
    backtest_error: zh ? "回测阶段需恢复" : "Backtest needs recovery",
  }[state.kind];

  return (
    <WorkbenchHeader
      eyebrow={zh ? "研究工作台" : "Research workbench"}
      title={<>{zh ? "因子" : "Factor"} <span className="font-normal text-tm-fg-2">Alpha</span></>}
      subtitle={zh ? "从假设到可检验表达式" : "From hypothesis to a testable expression"}
      statuses={[
        { label: zh ? "阶段" : "Stage", value: stage, tone: state.kind.includes("error") ? "negative" : state.kind === "done" ? "positive" : "default" },
        { label: zh ? "股票池" : "Universe", value: universe },
        { label: zh ? "数据面板" : "Data panel", value: zh ? "服务端缓存" : "Server cache", tone: "positive" },
      ]}
      action={result ? (
          <button type="button" onClick={onOpenBacktest} className="inline-flex items-center gap-2 border border-tm-accent px-3 py-1.5 text-[10px] text-tm-accent hover:bg-tm-accent hover:text-tm-bg">
            {zh ? "在回测中比较" : "Compare in Backtest"} <ArrowRight className="h-3.5 w-3.5" />
          </button>
        ) : undefined}
    />
  );
}
