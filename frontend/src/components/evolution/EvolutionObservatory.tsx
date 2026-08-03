"use client";

import { useMemo, useState } from "react";
import { ArrowRight, RotateCcw, ShieldCheck } from "lucide-react";

import type {
  EvolutionCalibration,
  EvolutionChange,
  EvolutionWeight,
  IcAnnotation,
  IcTrendResponse,
} from "@/lib/api/evolution";
import type { Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { ChangeHistoryTable } from "./ChangeHistoryTable";
import { IcTrendChart } from "./IcTrendChart";
import { ReliabilityChart } from "./ReliabilityChart";
import { WeightDeltaTable } from "./WeightDeltaTable";

type DetailTab = "weights" | "calibration" | "ledger";

function latestIc(points: Array<{ computed_at: string; ic: number }>): number | null {
  if (points.length === 0) return null;
  return [...points].sort((a, b) => a.computed_at.localeCompare(b.computed_at)).at(-1)?.ic ?? null;
}

function focusSignals(icTrend: IcTrendResponse | null, weights: EvolutionWeight[]): string[] {
  if (!icTrend) return [];
  const weightRisk = new Map<string, number>();
  for (const weight of weights) {
    const score = weight.consecutive_bad_windows * 10 + Math.max(0, 5 - weight.shadow_streak);
    weightRisk.set(weight.signal_name, Math.max(weightRisk.get(weight.signal_name) ?? 0, score));
  }
  return [...icTrend.series]
    .sort((a, b) => {
      const aIc = latestIc(a.points) ?? 0;
      const bIc = latestIc(b.points) ?? 0;
      const aScore = (weightRisk.get(a.signal_name) ?? 0) + (aIc < 0 ? Math.abs(aIc) * 100 : 0);
      const bScore = (weightRisk.get(b.signal_name) ?? 0) + (bIc < 0 ? Math.abs(bIc) * 100 : 0);
      return bScore - aScore;
    })
    .slice(0, 3)
    .map((series) => series.signal_name);
}

function weightFor(weights: EvolutionWeight[], signal: string, status: EvolutionWeight["status"]): EvolutionWeight | null {
  return weights.find((weight) => weight.signal_name === signal && weight.status === status) ?? null;
}

export default function EvolutionObservatory({
  locale,
  icTrend,
  annotations,
  weights,
  calibration,
  changes,
  pendingCount,
}: {
  locale: Locale;
  icTrend: IcTrendResponse | null;
  annotations: IcAnnotation[];
  weights: EvolutionWeight[];
  calibration: EvolutionCalibration | null;
  changes: EvolutionChange[];
  pendingCount: number;
}) {
  const zh = locale === "zh";
  const focus = useMemo(() => focusSignals(icTrend, weights), [icTrend, weights]);
  const [selectedSignal, setSelectedSignal] = useState<string | null>(focus[0] ?? null);
  const [detailTab, setDetailTab] = useState<DetailTab>("weights");
  const selected = selectedSignal && focus.includes(selectedSignal) ? selectedSignal : focus[0] ?? null;
  const focusedSeries = icTrend?.series.filter((series) => focus.includes(series.signal_name)) ?? [];
  const selectedSeries = icTrend?.series.find((series) => series.signal_name === selected) ?? null;
  const selectedIc = selectedSeries ? latestIc(selectedSeries.points) : null;
  const live = selected ? weightFor(weights, selected, "live") : null;
  const shadow = selected ? weightFor(weights, selected, "shadow") : null;
  const guarded = selected ? weightFor(weights, selected, "guarded_shadow") : null;
  const relatedChange = selected
    ? changes.find((change) => change.signal === selected || change.new_value.includes(selected)) ?? null
    : null;
  const signalNames = new Set(weights.map((weight) => weight.signal_name));
  const liveCount = new Set(weights.filter((weight) => weight.status === "live").map((weight) => weight.signal_name)).size;
  const shadowCount = new Set(weights.filter((weight) => weight.status === "shadow").map((weight) => weight.signal_name)).size;
  const guardedCount = new Set(weights.filter((weight) => weight.status === "guarded_shadow").map((weight) => weight.signal_name)).size;
  const promotedCount = changes.filter((change) => change.source === "auto_promote").length;
  const rolledBackCount = changes.filter((change) => change.source === "auto_rollback").length;
  const evidenceEvents = changes.map((change) => ({
    ts: change.changed_at,
    source: change.source,
    label: change.signal ? `${change.source}: ${change.signal}` : change.source,
  }));

  return (
    <section className="border-b border-tm-rule bg-tm-bg">
      <header className="flex min-h-14 items-center justify-between border-b border-tm-rule px-4 py-2">
        <div>
          <h1 className="text-[16px] font-semibold tracking-tight">
            {zh ? "演化监控" : "Evolution"} <span className="font-normal text-tm-fg-2">Model Change Observatory</span>
          </h1>
          <p className="mt-0.5 text-[10px] text-tm-muted">
            {pendingCount > 0
              ? (zh ? `${pendingCount} 项方法变化等待审查，图表只突出最需要关注的 3 个信号。` : `${pendingCount} methodology changes await review; only the 3 highest-attention signals are emphasized.`)
              : (zh ? "当前没有待审提议，继续关注样本外变化与保护机制。" : "No proposal awaits review; continue monitoring out-of-sample changes and guards.")}
          </p>
        </div>
        <a href="#evolution-review" className={`inline-flex items-center gap-2 px-3 py-2 text-[11px] font-semibold ${pendingCount > 0 ? "bg-tm-accent text-tm-bg hover:brightness-110" : "border border-tm-rule text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent"}`}>
          {pendingCount > 0 ? (zh ? "审查变化" : "Review changes") : (zh ? "查看演化工作流" : "View evolution workflow")} <ArrowRight className="h-3.5 w-3.5" />
        </a>
      </header>

      <div className="grid grid-cols-[minmax(620px,2fr)_minmax(300px,1fr)] border-b border-tm-rule">
        <div className="min-w-0 border-r border-tm-rule p-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">{zh ? "样本外表现" : "Out-of-sample performance"}</p>
              <p className="mt-1 text-[9px] text-tm-muted">{zh ? "按劣化窗口、负 IC 和保护状态确定关注顺序" : "Attention order uses degrading windows, negative IC, and guard state"}</p>
            </div>
            <div className="flex gap-1">
              {focus.map((signal) => (
                <button
                  key={signal}
                  type="button"
                  onClick={() => setSelectedSignal(signal)}
                  className={`border px-2 py-1 text-[9px] ${selected === signal ? "border-tm-accent bg-tm-accent/10 text-tm-accent" : "border-tm-rule text-tm-muted hover:text-tm-fg"}`}
                >
                  {getSignalDisplayLabel(signal, locale)}
                </button>
              ))}
            </div>
          </div>
          {icTrend && focusedSeries.length > 0 ? (
            <IcTrendChart series={focusedSeries} locale={locale} annotations={annotations.filter((item) => focus.includes(item.signal_name))} events={evidenceEvents} />
          ) : (
            <div className="flex h-64 items-center justify-center text-[10px] text-tm-muted">{zh ? "暂无可绘制的 IC 数据" : "No IC data available"}</div>
          )}
        </div>

        <aside className="min-w-0 bg-tm-bg-2/20 p-3">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">{zh ? "变化证据窗口" : "Change evidence window"}</p>
            <span className={selectedIc == null ? "text-tm-muted" : selectedIc >= 0 ? "text-tm-pos" : "text-tm-neg"}>
              IC {selectedIc == null ? "—" : `${selectedIc >= 0 ? "+" : ""}${selectedIc.toFixed(3)}`}
            </span>
          </div>
          <h2 className="mt-3 text-[16px] font-semibold">{selected ? getSignalDisplayLabel(selected, locale) : (zh ? "没有可选信号" : "No signal selected")}</h2>
          <div className="mt-3 grid grid-cols-3 gap-px border border-tm-rule bg-tm-rule text-center text-[9px]">
            {[
              [zh ? "LIVE" : "LIVE", live?.weight],
              [zh ? "SHADOW" : "SHADOW", shadow?.weight],
              [zh ? "GUARDED" : "GUARDED", guarded?.weight],
            ].map(([label, value]) => (
              <div key={String(label)} className="bg-tm-bg px-1 py-2">
                <p className="text-tm-muted">{label}</p>
                <p className="mt-1 font-mono text-[12px] text-tm-fg">{typeof value === "number" ? value.toFixed(4) : "—"}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 space-y-2 border-t border-tm-rule pt-3 text-[9.5px] leading-4">
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "劣化窗口" : "Degrading windows"}</span><span>{live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows ?? 0}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "晋升累计" : "Promotion streak"}</span><span>{shadow?.shadow_streak ?? 0}/5</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "最近同期事件" : "Latest co-occurring event"}</span><span className="max-w-[180px] truncate text-right" title={relatedChange?.source}>{relatedChange?.source ?? (zh ? "未记录" : "Not recorded")}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "事件时间" : "Event time"}</span><span>{relatedChange?.changed_at ? new Date(relatedChange.changed_at).toLocaleString(zh ? "zh-CN" : "en-US") : "—"}</span></div>
          </div>
          <p className="mt-3 border-l-2 border-tm-warn pl-2 text-[9px] leading-4 text-tm-muted">
            {zh ? "这里只展示真实共现记录和前后 IC，不把相关性写成因果。" : "Only recorded co-occurrence and before/after IC are shown; correlation is not described as causation."}
          </p>
        </aside>
      </div>

      <div className="grid grid-cols-5 gap-px border-b border-tm-rule bg-tm-rule text-[9px]">
        {[
          ["LIVE", liveCount],
          ["SHADOW", shadowCount],
          ["GUARDED", guardedCount],
          [zh ? "已晋升" : "PROMOTED", promotedCount],
          [zh ? "已回滚" : "ROLLED BACK", rolledBackCount],
        ].map(([label, count], index) => (
          <div key={String(label)} className="relative bg-tm-bg px-3 py-2.5">
            <p className="text-tm-muted">{label}</p>
            <p className="mt-1 font-mono text-[17px] text-tm-fg">{count}</p>
            {index < 4 ? <ArrowRight className="absolute -right-2 top-5 z-10 h-3 w-3 bg-tm-bg text-tm-muted" /> : null}
          </div>
        ))}
      </div>

      <div className="border-b border-tm-rule">
        <div className="flex h-9 items-center gap-1 border-b border-tm-rule px-3">
          {(["weights", "calibration", "ledger"] as DetailTab[]).map((tab) => (
            <button key={tab} type="button" onClick={() => setDetailTab(tab)} className={`h-full border-b-2 px-3 text-[10px] ${detailTab === tab ? "border-tm-accent text-tm-accent" : "border-transparent text-tm-muted hover:text-tm-fg"}`}>
              {tab === "weights" ? (zh ? "权重差异" : "Weight deltas") : tab === "calibration" ? (zh ? "置信校准" : "Calibration") : (zh ? "变更账本" : "Change ledger")}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-1 text-[9px] text-tm-muted"><ShieldCheck className="h-3 w-3" /> {signalNames.size} {zh ? "个信号受控" : "signals governed"}</span>
        </div>
        <div className="p-3">
          {detailTab === "weights" ? <WeightDeltaTable weights={weights} locale={locale} /> : null}
          {detailTab === "calibration" ? calibration ? <ReliabilityChart calibration={calibration} locale={locale} /> : <p className="py-8 text-center text-[10px] text-tm-muted">{zh ? "暂无校准数据" : "No calibration data"}</p> : null}
          {detailTab === "ledger" ? <ChangeHistoryTable changes={changes.slice(0, 20)} locale={locale} /> : null}
        </div>
      </div>

      <div className="flex min-h-7 items-center justify-between px-3 text-[9px] text-tm-muted">
        <span>{zh ? "60 秒缓存 · 默认只绘制 3 条重点信号 · 详情按需切换" : "60s cache · 3 focus signals by default · details on demand"}</span>
        <span className="inline-flex items-center gap-1"><RotateCcw className="h-3 w-3" /> {zh ? "所有变化保留回滚与审计记录" : "Every change retains rollback and audit history"}</span>
      </div>
    </section>
  );
}
