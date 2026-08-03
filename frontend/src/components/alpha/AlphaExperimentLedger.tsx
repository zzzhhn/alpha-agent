"use client";

import { Clock3, Star } from "lucide-react";

import { useLocale } from "@/components/layout/LocaleProvider";
import type { HypothesisHistoryEntry } from "@/lib/types";

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
      <div className="flex h-9 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">{zh ? "最近研究记录" : "Recent research records"}</p>
        <span className="text-[9px] text-tm-muted">{zh ? "重开不会自动重跑" : "Reopen does not auto-run"}</span>
      </div>
      {history.length === 0 ? (
        <p className="px-3 py-5 text-center text-[10px] text-tm-muted">{zh ? "完成一次表达式生成后，研究记录会出现在这里。" : "A research record appears here after expression generation."}</p>
      ) : (
        <div className="divide-y divide-tm-rule">
          {history.slice(0, 5).map((entry) => (
            <button key={entry.id} type="button" onClick={() => onOpen(entry)} className="grid w-full grid-cols-[150px_minmax(240px,1fr)_minmax(240px,1fr)_100px] items-center gap-3 px-3 py-2 text-left text-[9.5px] hover:bg-tm-bg-2">
              <span className="flex items-center gap-1 text-tm-muted"><Clock3 className="h-3 w-3" /> {new Date(entry.timestamp).toLocaleString(zh ? "zh-CN" : "en-US")}</span>
              <span className="truncate text-tm-fg" title={entry.request.text}>{entry.request.text}</span>
              <code className="truncate text-tm-fg-2" title={entry.result.spec.expression}>{entry.result.spec.expression}</code>
              <span className="text-right text-tm-muted">{entry.isFavorite ? <Star className="ml-auto h-3 w-3 fill-tm-warn text-tm-warn" /> : entry.request.universe}</span>
            </button>
          ))}
        </div>
      )}
      <p className="border-t border-tm-rule px-3 py-2 text-[9px] text-tm-muted">{zh ? "历史文本保存在当前浏览器；回测指标仍以服务端真实结果为准。" : "History text is browser-local; backtest metrics remain authoritative from the server result."}</p>
    </section>
  );
}
