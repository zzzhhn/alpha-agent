"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ArrowRight, RotateCcw, ShieldCheck } from "lucide-react";

import type {
  EvolutionCalibration,
  EvolutionChange,
  EvolutionWeight,
  IcAnnotation,
  IcTrendResponse,
} from "@/lib/api/evolution";
import type { Locale } from "@/lib/i18n";
import type { EvolutionHealth, HealthTone } from "@/lib/evolution-health";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { formatUtc8DateTime } from "@/lib/format-datetime";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { DecisionStrip } from "@/components/workbench/DecisionStrip";
import { ChangeHistoryTable } from "./ChangeHistoryTable";
import { IcTrendChart } from "./IcTrendChart";
import { ReliabilityChart } from "./ReliabilityChart";
import { WeightDeltaTable } from "./WeightDeltaTable";

type DetailTab = "weights" | "calibration" | "ledger";

function healthTone(tone: HealthTone): "default" | "positive" | "warning" | "negative" {
  if (tone === "good") return "positive";
  if (tone === "warn") return "warning";
  if (tone === "action") return "negative";
  return "default";
}

function numericFact(health: EvolutionHealth, section: keyof EvolutionHealth, key: string): number | null {
  const value = health[section].facts[key];
  return typeof value === "number" ? value : null;
}

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
  health,
  icTrend,
  annotations,
  weights,
  calibration,
  changes,
  pendingCount,
  children,
}: {
  locale: Locale;
  health: EvolutionHealth;
  icTrend: IcTrendResponse | null;
  annotations: IcAnnotation[];
  weights: EvolutionWeight[];
  calibration: EvolutionCalibration | null;
  changes: EvolutionChange[];
  pendingCount: number;
  children?: ReactNode;
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
  const latestUpdate = [calibration?.as_of, ...changes.map((change) => change.changed_at)]
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;
  const brier = numericFact(health, "calibration", "brier");
  const positiveIc = numericFact(health, "ic", "pos");
  const totalIc = numericFact(health, "ic", "total");
  const degrading = numericFact(health, "weights", "degrading");

  return (
    <section className="border-b border-tm-rule bg-tm-bg">
      <WorkbenchHeader
        eyebrow={zh ? "高级研究工具" : "Advanced research tools"}
        title={zh ? "演化监控" : "Evolution monitor"}
        subtitle={zh ? "观察样本外变化，审查每一次模型调整" : "Observe out-of-sample change and review every model adjustment"}
        statuses={[
          { label: zh ? "最后更新" : "Last update", value: formatUtc8DateTime(latestUpdate) },
          { label: zh ? "评估健康" : "Evaluation", value: totalIc ? `${positiveIc ?? 0}/${totalIc} +IC` : (zh ? "无数据" : "NO DATA"), tone: healthTone(health.ic.tone) },
          { label: zh ? "计算预算" : "Compute budget", value: zh ? "60 秒缓存" : "60S CACHE", tone: "positive" },
          { label: zh ? "待审提议" : "Pending", value: String(pendingCount), tone: pendingCount > 0 ? "negative" : "positive" },
        ]}
      />

      <DecisionStrip
        headline={pendingCount > 0
          ? (zh ? `整体可用，${pendingCount} 项变化需要审查` : `System available; ${pendingCount} change requires review`)
          : degrading && degrading > 0
            ? (zh ? `整体可用，${degrading} 个信号正在劣化` : `System available; ${degrading} signals are degrading`)
            : (zh ? "整体可用，当前没有待审变化" : "System available; no change awaits review")}
        description={zh ? "只突出三条决策相关信号，所有事件仅作同期相关性线索。" : "Only three decision-relevant signals are emphasized; events remain contemporaneous evidence."}
        metrics={[
          { label: zh ? "校准" : "Calibration", value: brier === null ? "—" : brier.toFixed(3), detail: "Brier", tone: healthTone(health.calibration.tone) },
          { label: "IC (20D)", value: selectedIc === null ? "—" : `${selectedIc >= 0 ? "+" : ""}${selectedIc.toFixed(3)}`, detail: selected ? getSignalDisplayLabel(selected, locale) : undefined, tone: selectedIc === null ? "default" : selectedIc >= 0 ? "positive" : "negative" },
          { label: zh ? "权重自调节" : "Adaptive weights", value: degrading ?? "—", detail: zh ? "劣化信号" : "degrading signals", tone: healthTone(health.weights.tone) },
          { label: zh ? "提议状态" : "Proposals", value: pendingCount, detail: zh ? "等待人工审查" : "awaiting review", tone: pendingCount > 0 ? "negative" : "positive" },
        ]}
        action={<a href="#evolution-review" className={`inline-flex h-11 items-center gap-2 px-4 text-[11px] font-semibold ${pendingCount > 0 ? "bg-tm-accent text-tm-bg hover:brightness-110" : "border border-tm-rule text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent"}`}>{pendingCount > 0 ? (zh ? "审查变化" : "Review changes") : (zh ? "查看演化工作流" : "View workflow")} <ArrowRight className="h-3.5 w-3.5" /></a>}
      />

      <div className="grid grid-cols-[minmax(720px,2fr)_minmax(380px,1fr)] gap-4 border-b border-tm-rule px-6 py-4">
        <div className="min-w-0 border border-tm-rule p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[12px] font-semibold tracking-[0.08em] text-tm-fg">{zh ? "样本外表现时间线" : "Out-of-sample performance timeline"}</p>
              <p className="mt-1 text-[10px] text-tm-muted">{zh ? "按劣化窗口、负 IC 和保护状态确定关注顺序" : "Attention order uses degrading windows, negative IC, and guard state"}</p>
            </div>
            <div className="flex gap-1">
              {focus.map((signal) => (
                <button
                  key={signal}
                  type="button"
                  onClick={() => setSelectedSignal(signal)}
                  className={`border px-2.5 py-1.5 text-[10px] ${selected === signal ? "border-tm-accent bg-tm-accent/10 text-tm-accent" : "border-tm-rule text-tm-muted hover:text-tm-fg"}`}
                >
                  {getSignalDisplayLabel(signal, locale)}
                </button>
              ))}
            </div>
          </div>
          {icTrend && focusedSeries.length > 0 ? (
            <IcTrendChart series={focusedSeries} locale={locale} annotations={annotations.filter((item) => focus.includes(item.signal_name))} events={evidenceEvents} height={430} />
          ) : (
            <div className="flex h-[220px] items-center justify-center border-t border-tm-rule text-[11px] text-tm-muted">{zh ? "暂无可绘制的 IC 数据，健康结论已降级为无数据。" : "No IC data is available; the health verdict is explicitly unavailable."}</div>
          )}
        </div>

        <aside className="min-w-0 border border-tm-rule bg-tm-bg-2/20 p-4">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-semibold tracking-[0.08em] text-tm-fg">{zh ? "本次变化证据" : "Current change evidence"}</p>
            <span className={selectedIc == null ? "text-tm-muted" : selectedIc >= 0 ? "text-tm-pos" : "text-tm-neg"}>
              IC {selectedIc == null ? "—" : `${selectedIc >= 0 ? "+" : ""}${selectedIc.toFixed(3)}`}
            </span>
          </div>
          <h2 className="mt-4 text-[20px] font-semibold">{selected ? getSignalDisplayLabel(selected, locale) : (zh ? "没有可选信号" : "No signal selected")}</h2>
          <div className="mt-3 grid grid-cols-3 gap-px border border-tm-rule bg-tm-rule text-center text-[9px]">
            {[
              [zh ? "LIVE" : "LIVE", live?.weight],
              [zh ? "SHADOW" : "SHADOW", shadow?.weight],
              [zh ? "GUARDED" : "GUARDED", guarded?.weight],
            ].map(([label, value]) => (
              <div key={String(label)} className="bg-tm-bg px-1 py-3">
                <p className="text-tm-muted">{label}</p>
                <p className="mt-1 font-mono text-[15px] text-tm-fg">{typeof value === "number" ? value.toFixed(4) : "—"}</p>
              </div>
            ))}
          </div>
          {selectedSeries && selectedSeries.points.length > 1 ? (
            <SignalSparkline
              points={selectedSeries.points}
              label={zh ? "IC（滚动 20D）" : "IC (rolling 20D)"}
            />
          ) : null}
          <div className="mt-4 space-y-3 border-t border-tm-rule pt-4 text-[10.5px] leading-5">
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "校准（Brier）" : "Calibration (Brier)"}</span><span>{brier == null ? "—" : brier.toFixed(3)}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "证据窗口" : "Evidence window"}</span><span>{selectedSeries?.points.length ?? 0} {zh ? "个观测" : "observations"}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "劣化窗口" : "Degrading windows"}</span><span>{live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows ?? 0}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "晋升累计" : "Promotion streak"}</span><span>{shadow?.shadow_streak ?? 0}/5</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "最近同期事件" : "Latest co-occurring event"}</span><span className="max-w-[180px] truncate text-right" title={relatedChange?.source}>{relatedChange?.source ?? (zh ? "未记录" : "Not recorded")}</span></div>
            <div className="flex justify-between gap-4"><span className="text-tm-muted">{zh ? "事件时间" : "Event time"}</span><span>{formatUtc8DateTime(relatedChange?.changed_at, { year: "numeric", seconds: true })}</span></div>
          </div>
          <p className="mt-4 border-l-2 border-tm-warn pl-3 text-[9.5px] leading-5 text-tm-muted">
            {zh ? "这里只展示真实共现记录和前后 IC，不把相关性写成因果。" : "Only recorded co-occurrence and before/after IC are shown; correlation is not described as causation."}
          </p>
        </aside>
      </div>

      <div className="border-b border-tm-rule px-6 py-4">
        <p className="mb-3 text-[12px] font-semibold tracking-[0.08em] text-tm-fg">{zh ? "晋升漏斗（当前批次）" : "Promotion funnel (current cohort)"}</p>
        <div className="grid grid-cols-5 gap-3 text-[10px]">
        {[
          ["LIVE", liveCount],
          ["SHADOW", shadowCount],
          ["GUARDED", guardedCount],
          [zh ? "已晋升" : "PROMOTED", promotedCount],
          [zh ? "已回滚" : "ROLLED BACK", rolledBackCount],
        ].map(([label, count], index) => (
          <div key={String(label)} className={`relative flex min-h-[88px] flex-col items-center justify-center border bg-tm-bg ${index === 2 && Number(count) > 0 ? "border-tm-warn" : "border-tm-rule"}`}>
            <p className="text-tm-muted">{label}</p>
            <p className={`mt-2 font-mono text-[22px] ${index === 2 && Number(count) > 0 ? "text-tm-warn" : "text-tm-fg"}`}>{count}</p>
            {index < 4 ? <ArrowRight className="absolute -right-5 top-9 z-10 h-4 w-4 bg-tm-bg text-tm-muted" /> : null}
          </div>
        ))}
        </div>
      </div>

      {children}

      <details className="border-b border-tm-rule">
        <summary className="flex h-11 cursor-pointer list-none items-center justify-between px-6 text-[11px] text-tm-muted hover:text-tm-fg">
          <span>{zh ? "展开权重、校准与完整变更明细" : "Expand weights, calibration, and full change details"}</span>
          <span>{zh ? "按需加载视图" : "On-demand view"}</span>
        </summary>
        <div className="flex h-11 items-center gap-1 border-y border-tm-rule px-6">
          {(["weights", "calibration", "ledger"] as DetailTab[]).map((tab) => (
            <button key={tab} type="button" onClick={() => setDetailTab(tab)} className={`h-full border-b-2 px-4 text-[11px] ${detailTab === tab ? "border-tm-accent text-tm-accent" : "border-transparent text-tm-muted hover:text-tm-fg"}`}>
              {tab === "weights" ? (zh ? "权重差异" : "Weight deltas") : tab === "calibration" ? (zh ? "置信校准" : "Calibration") : (zh ? "变更账本" : "Change ledger")}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-1 text-[9px] text-tm-muted"><ShieldCheck className="h-3 w-3" /> {signalNames.size} {zh ? "个信号受控" : "signals governed"}</span>
        </div>
        <div className="px-6 py-4">
          {detailTab === "weights" ? <WeightDeltaTable weights={weights} locale={locale} /> : null}
          {detailTab === "calibration" ? calibration ? <ReliabilityChart calibration={calibration} locale={locale} /> : <p className="py-8 text-center text-[10px] text-tm-muted">{zh ? "暂无校准数据" : "No calibration data"}</p> : null}
          {detailTab === "ledger" ? <ChangeHistoryTable changes={changes.slice(0, 20)} locale={locale} /> : null}
        </div>
      </details>

      <div className="flex min-h-7 items-center justify-between px-3 text-[9px] text-tm-muted">
        <span>{zh ? "60 秒缓存 · 默认只绘制 3 条重点信号 · 详情按需切换" : "60s cache · 3 focus signals by default · details on demand"}</span>
        <span className="inline-flex items-center gap-1"><RotateCcw className="h-3 w-3" /> {zh ? "所有变化保留回滚与审计记录" : "Every change retains rollback and audit history"}</span>
      </div>
    </section>
  );
}

function SignalSparkline({ points, label }: { readonly points: readonly { computed_at: string; ic: number }[]; readonly label: string }) {
  const values = points.map((point) => point.ic);
  const min = Math.min(...values, -0.01);
  const max = Math.max(...values, 0.01);
  const range = Math.max(max - min, 0.001);
  const polyline = points.map((point, index) => {
    const x = 8 + (index / Math.max(points.length - 1, 1)) * 284;
    const y = 78 - ((point.ic - min) / range) * 62;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const zeroY = 78 - ((0 - min) / range) * 62;
  return (
    <div className="mt-3 border border-tm-rule bg-tm-bg px-3 py-2">
      <div className="flex items-center justify-between text-[9px] uppercase tracking-[0.08em] text-tm-muted"><span>{label}</span><span>{points.length} obs</span></div>
      <svg viewBox="0 0 300 86" className="mt-2 h-[96px] w-full" role="img" aria-label={label}>
        <line x1="8" x2="292" y1={zeroY} y2={zeroY} stroke="currentColor" className="text-tm-rule" strokeDasharray="3 3" />
        <polyline points={polyline} fill="none" stroke="currentColor" className="text-tm-pos" strokeWidth="2" />
      </svg>
    </div>
  );
}
