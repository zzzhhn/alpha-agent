"use client";

/**
 * B4 (2026-05-19) lasso-replacement panel.
 *
 * UI for the "why did this stock move?" question: user picks a date range,
 * clicks Generate, and the backend pulls events in the window + asks the
 * BYOK LLM to identify which event(s) most likely drove the price move.
 * Response is cached server-side per (user, ticker, from, to, language)
 * so a re-click on the same window is sub-100ms and zero LLM cost (B3).
 *
 * Date pickers replace the lasso UI from the Phase 3 spec — lasso on
 * lightweight-charts requires custom mouse-event plumbing that's a v2
 * polish, not blocking for v1 utility.
 */

import { useCallback, useState } from "react";
import { Sparkles } from "lucide-react";

import {
  explainRange,
  type ExplainRangeResponse,
} from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";

type Status = "idle" | "loading" | "done" | "error";

function defaultFrom(): string {
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
}

function defaultTo(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ExplainRangePanel({ ticker }: { ticker: string }) {
  const { locale } = useLocale();
  const [fromTs, setFromTs] = useState(defaultFrom);
  const [toTs, setToTs] = useState(defaultTo);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<ExplainRangeResponse | null>(null);
  const [errMsg, setErrMsg] = useState("");

  const onGenerate = useCallback(async () => {
    if (fromTs > toTs) {
      setErrMsg(
        locale === "zh" ? "起始日期需 <= 结束日期" : "From date must be <= to date",
      );
      setStatus("error");
      return;
    }
    setStatus("loading");
    setErrMsg("");
    try {
      const res = await explainRange(ticker, fromTs, toTs, locale);
      setResult(res);
      setStatus("done");
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, [ticker, fromTs, toTs, locale]);

  const copy =
    locale === "zh"
      ? {
          title: "区间事件解读",
          from: "从",
          to: "至",
          button: "用 LLM 分析此区间",
          loading: "生成中...",
          empty: "无可解读的事件",
          cacheHit: "(命中缓存)",
          eventCount: (n: number) => `基于 ${n} 个事件`,
        }
      : {
          title: "Range Event Explainer",
          from: "From",
          to: "To",
          button: "Explain with LLM",
          loading: "Generating...",
          empty: "No events to explain",
          cacheHit: "(cache hit)",
          eventCount: (n: number) => `Based on ${n} events`,
        };

  return (
    <div className="mt-4 rounded border border-tm-rule bg-tm-bg-3/40 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-tm-fg flex items-center gap-1">
          <Sparkles aria-hidden className="h-3.5 w-3.5 text-tm-accent" strokeWidth={1.75} />
          {copy.title}
        </h3>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-1 text-tm-fg-2">
          {copy.from}
          <input
            type="date"
            value={fromTs}
            onChange={(e) => setFromTs(e.target.value)}
            max={toTs}
            className="rounded border border-tm-rule bg-tm-bg px-1.5 py-0.5 font-tm-mono text-[11px] text-tm-fg"
          />
        </label>
        <label className="flex items-center gap-1 text-tm-fg-2">
          {copy.to}
          <input
            type="date"
            value={toTs}
            onChange={(e) => setToTs(e.target.value)}
            min={fromTs}
            max={defaultTo()}
            className="rounded border border-tm-rule bg-tm-bg px-1.5 py-0.5 font-tm-mono text-[11px] text-tm-fg"
          />
        </label>
        <button
          type="button"
          onClick={onGenerate}
          disabled={status === "loading"}
          className="rounded border border-tm-rule bg-tm-bg px-2.5 py-0.5 text-xs text-tm-fg hover:border-tm-accent disabled:opacity-50"
        >
          {status === "loading" ? copy.loading : copy.button}
        </button>
      </div>
      {status === "error" ? (
        <div className="text-xs text-tm-neg">{errMsg}</div>
      ) : null}
      {status === "done" && result ? (
        <div className="space-y-1">
          <p className="text-sm leading-relaxed text-tm-fg">
            {result.explanation}
          </p>
          <p className="text-[11px] text-tm-muted">
            {copy.eventCount(result.event_count)}
            {result.cache === "hit" ? ` ${copy.cacheHit}` : null}
          </p>
        </div>
      ) : null}
    </div>
  );
}
