"use client";

import { ArrowRight, Database, FlaskConical, GitBranch } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";
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
    <section className="border border-tm-rule bg-tm-bg">
      <header className="flex min-h-14 items-center justify-between border-b border-tm-rule px-4 py-2">
        <div>
          <h1 className="text-[16px] font-semibold tracking-tight">
            {zh ? "因子" : "Factor"} <span className="font-normal text-tm-fg-2">Factor Decision Workbench</span>
          </h1>
          <p className="mt-0.5 text-[10px] text-tm-muted">{zh ? "把一个研究假设变成可反驳、可比较、可追踪的候选因子。" : "Turn one research hypothesis into a falsifiable, comparable, traceable factor candidate."}</p>
        </div>
        {result ? (
          <button type="button" onClick={onOpenBacktest} className="inline-flex items-center gap-2 border border-tm-accent px-3 py-1.5 text-[10px] text-tm-accent hover:bg-tm-accent hover:text-tm-bg">
            {zh ? "在回测中比较" : "Compare in Backtest"} <ArrowRight className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </header>
      <div className="grid grid-cols-4 gap-px bg-tm-rule text-[9.5px]">
        <div className="bg-tm-bg-2/40 px-3 py-2">
          <p className="flex items-center gap-1 text-tm-muted"><FlaskConical className="h-3 w-3" /> {zh ? "当前阶段" : "Stage"}</p>
          <p className="mt-1 text-tm-fg">{stage}</p>
        </div>
        <div className="bg-tm-bg-2/40 px-3 py-2">
          <p className="flex items-center gap-1 text-tm-muted"><Database className="h-3 w-3" /> {zh ? "研究股票池" : "Universe"}</p>
          <p className="mt-1 text-tm-fg">{universe} · {zh ? "缓存面板" : "cached panel"}</p>
        </div>
        <div className="bg-tm-bg-2/40 px-3 py-2">
          <p className="flex items-center gap-1 text-tm-muted"><GitBranch className="h-3 w-3" /> {zh ? "表达式血缘" : "Expression lineage"}</p>
          <p className="mt-1 truncate text-tm-fg" title={result?.spec.expression}>{result ? `${result.spec.operators_used.length} ops · ${result.spec.lookback}d` : (zh ? "运行后生成" : "Generated on run")}</p>
        </div>
        <div className="bg-tm-bg-2/40 px-3 py-2">
          <p className="text-tm-muted">{zh ? "记录范围" : "Record scope"}</p>
          <p className="mt-1 text-tm-fg">{zh ? "本机研究历史 + 服务端本次结果" : "Local research history + current server result"}</p>
        </div>
      </div>
    </section>
  );
}
