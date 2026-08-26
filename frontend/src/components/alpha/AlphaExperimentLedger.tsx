"use client";

import { Clock3, Star } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";
import type { HypothesisHistoryEntry } from "@/lib/types";
import { TmRowButton } from "@/components/tm/TmButton";

export function AlphaExperimentLedger({
  history,
  onOpen,
}: {
  readonly history: readonly HypothesisHistoryEntry[];
  readonly onOpen: (entry: HypothesisHistoryEntry) => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";

  return (
    <section className="border border-tm-rule bg-tm-bg">
      <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4">
        <p className="text-[12px] font-semibold tracking-[0.08em] text-tm-fg"><span className="mr-2 text-tm-accent">④</span>{zh ? "最近实验" : "Recent experiments"}</p>
        <span className="text-xs text-tm-muted">{zh ? "重开不会自动重跑" : "Reopen does not auto-run"}</span>
      </div>
      {history.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-tm-muted">{zh ? "完成一次表达式生成后，研究记录会出现在这里。" : "A research record appears here after expression generation."}</p>
      ) : (
        <div>
          <div className="grid min-h-8 grid-cols-[170px_minmax(260px,1.2fr)_minmax(260px,1fr)_110px] items-center gap-4 border-b border-tm-rule bg-tm-bg-2/30 px-4 text-xs uppercase tracking-[0.08em] text-tm-muted">
            <span>{zh ? "时间" : "Time"}</span>
            <span>{zh ? "研究假设" : "Hypothesis"}</span>
            <span>{zh ? "表达式" : "Expression"}</span>
            <span className="text-right">{zh ? "操作" : "Action"}</span>
          </div>
          <div className="divide-y divide-tm-rule">
          {history.slice(0, 5).map((entry) => (
            <TmRowButton key={entry.id} onClick={() => onOpen(entry)} className="grid min-h-11 grid-cols-[170px_minmax(260px,1.2fr)_minmax(260px,1fr)_110px] items-center gap-4 px-4 py-2 text-xs">
              <span className="flex items-center gap-1 text-tm-muted"><Clock3 className="h-3 w-3" /> {new Date(entry.timestamp).toLocaleString(zh ? "zh-CN" : "en-US")}</span>
              <span className="truncate text-tm-fg" title={entry.request.text}>{entry.request.text}</span>
              <code className="truncate text-tm-fg-2" title={entry.result.spec.expression}>{entry.result.spec.expression}</code>
              <span className="flex items-center justify-end gap-2 text-right text-tm-muted">{entry.isFavorite ? <Star className="h-3 w-3 fill-tm-warn text-tm-warn" /> : entry.request.universe}<span className="border border-tm-rule px-2 py-0.5 text-xs text-tm-fg-2">{zh ? "重开" : "Reopen"}</span></span>
            </TmRowButton>
          ))}
          </div>
        </div>
      )}
      <p className="border-t border-tm-rule px-3 py-2 text-xs text-tm-muted">{zh ? "历史文本保存在当前浏览器；回测指标仍以服务端真实结果为准。" : "History text is browser-local; backtest metrics remain authoritative from the server result."}</p>
    </section>
  );
}
