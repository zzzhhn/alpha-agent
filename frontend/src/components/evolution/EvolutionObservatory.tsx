"use client";

import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ArrowRight } from "lucide-react";

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
import { GlossaryTip } from "@/components/zoo/GlossaryTip";
import { IcTrendChart } from "./IcTrendChart";
import { ReliabilityChart } from "./ReliabilityChart";
import { WeightDeltaTable } from "./WeightDeltaTable";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { TmLinkButton } from "@/components/tm/TmButton";
import { EvolutionUnavailable } from "./EvolutionUnavailable";
import type { pendingReviewCounts } from "./review-state";
import { hasEnoughIcObservations, selectFocusSignals } from "./observatory-model";

type DetailTab = "weights" | "calibration";

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
  review,
  failures = [],
  children,
}: {
  locale: Locale;
  health: EvolutionHealth;
  icTrend: IcTrendResponse | null;
  annotations: IcAnnotation[];
  weights: EvolutionWeight[];
  calibration: EvolutionCalibration | null;
  changes: EvolutionChange[];
  review: ReturnType<typeof pendingReviewCounts>;
  failures?: readonly string[];
  children?: ReactNode;
}) {
  const zh = locale === "zh";
  const focus = useMemo(() => selectFocusSignals(weights, changes, Date.now()), [weights, changes]);
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
    ? changes.find((change) => change.signal === selected) ?? null
    : null;
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
  const latestUpdate = [calibration?.as_of, ...weights.map((weight) => weight.last_updated), ...changes.map((change) => change.changed_at), ...(icTrend?.series.flatMap((series) => series.points.map((point) => point.computed_at)) ?? [])]
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;
  const brier = numericFact(health, "calibration", "brier");
  const positiveIc = numericFact(health, "ic", "pos");
  const totalIc = numericFact(health, "ic", "total");
  const degrading = numericFact(health, "weights", "degrading");
  const evidenceMissing = !totalIc || brier === null || degrading === null;
  const pendingLabel = review.total !== null ? String(review.total) : review.known > 0 ? `≥${review.known}` : (zh ? "未知" : "Unknown");
  const unavailable = zh ? "不可用" : "Unavailable";
  const noEvidence = zh ? "无数据" : "No data";
  const countText = (count: number | null) => count === null ? unavailable : String(count);
  const hasChangeData = !failures.includes("change ledger");
  const hasWeightData = !failures.includes("weights");
  const verdict = review.known > 0
    ? review.total === null
      ? (zh ? `至少 ${review.known} 项变化待审查` : `At least ${review.known} await review`)
      : (zh ? `${review.total} 项变化待审查` : `${review.total} await review`)
    : review.total === null
      ? (zh ? "待审状态未确认" : "Review status unconfirmed")
      : evidenceMissing
        ? (zh ? "证据不足，无法评估整体表现" : "Insufficient evidence to assess performance")
        : health.ic.tone === "warn" || health.calibration.tone === "warn" || health.weights.tone === "warn"
          ? (zh ? "评估证据有警示" : "Evaluation evidence shows warnings")
          : (zh ? "当前没有待审变化" : "No changes await review");

  return (
    <section className="border-b border-tm-rule bg-tm-bg">
      <WorkbenchHeader
        eyebrow={zh ? "高级研究工具" : "Advanced research tools"}
        title={zh ? "演化监控" : "Evolution monitor"}
        subtitle={zh ? "样本外证据与变更审查" : "Out-of-sample evidence and change review"}
        statuses={[
          { label: zh ? "最新证据时间" : "Latest evidence", value: latestUpdate ? formatUtc8DateTime(latestUpdate) : noEvidence },
          { label: zh ? "正 IC 信号" : "Positive IC signals", value: totalIc ? `${positiveIc ?? 0}/${totalIc}` : noEvidence, tone: totalIc ? healthTone(health.ic.tone) : "warning" },
          { label: zh ? "待审（已加载）" : "Pending (loaded)", value: pendingLabel, tone: review.total === null || review.known > 0 ? "warning" : "default" },
        ]}
      />

      <DecisionStrip
        headline={verdict}
        description={review.known > 0 && evidenceMissing ? (zh ? "评估证据不完整。" : "Evaluation evidence is incomplete.") : undefined}
        metrics={[
          { label: zh ? "方法论因子" : "Methodology factors", value: countText(review.methodology), tone: review.methodology !== 0 ? "warning" : "default" },
          { label: zh ? "策略参数" : "Policy parameters", value: countText(review.policy), tone: review.policy !== 0 ? "warning" : "default" },
          { label: zh ? "校准" : "Calibration", value: brier === null ? (calibration === null ? unavailable : !calibration.applied ? (zh ? "未应用" : "Not applied") : noEvidence) : <GlossaryTip term="BRIER">{brier.toFixed(3)}</GlossaryTip>, detail: "Brier", tone: healthTone(health.calibration.tone) },
          { label: zh ? "劣化权重记录" : "Degrading weight records", value: degrading ?? (hasWeightData ? noEvidence : unavailable), tone: healthTone(health.weights.tone) },
        ]}
        action={<TmLinkButton href="#evolution-review" variant={review.known > 0 ? "primary" : "secondary"} size="md">{zh ? "审查变化" : "Review changes"}<ArrowRight aria-hidden="true" className="h-3.5 w-3.5" /></TmLinkButton>}
      />

      <div className="grid grid-cols-1 gap-3 border-b border-tm-rule px-4 py-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:px-6">
        <div className="min-w-0 border border-tm-rule px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-tm-mono text-xs font-semibold text-tm-fg">{zh ? "样本外表现时间线" : "Out-of-sample performance timeline"}{icTrend && selected ? (zh ? ` · ${icTrend.horizon_days} 日远期` : ` · ${icTrend.horizon_days}D forward`) : ""}</h2>
            {selected ? (
              <TmToggleGroup
                value={selected}
                onChange={setSelectedSignal}
                ariaLabel={zh ? "重点信号" : "Focus signal"}
                options={focus.map((signal) => ({
                  value: signal,
                  label: getSignalDisplayLabel(signal, locale),
                }))}
              />
            ) : null}
          </div>
          {icTrend === null ? (
            <EvolutionUnavailable locale={locale} message={zh ? "无法读取 IC 时间线。" : "Could not load the IC timeline."} />
          ) : focusedSeries.length > 0 ? (
            <IcTrendChart series={focusedSeries} locale={locale} annotations={annotations.filter((item) => focus.includes(item.signal_name))} events={evidenceEvents} height={300} />
          ) : (
            <p className="mt-1 text-xs leading-5 text-tm-muted">{zh ? "近 30 天未返回可绘制的 " : "No plottable "}<GlossaryTip term="IC OOS">IC</GlossaryTip>{zh ? " 观测。" : " observations in the last 30 days."}</p>
          )}
          {failures.includes("IC annotations") ? <p className="mt-1 text-xs text-tm-warn">{zh ? "IC 注释不可用。" : "IC annotations unavailable."}</p> : null}
        </div>

        <aside className="min-w-0 border border-tm-rule bg-tm-bg-2/20 px-3 py-2">
          <div className="flex items-center justify-between">
            <h2 className="font-tm-mono text-xs font-semibold text-tm-fg">{zh ? "信号证据" : "Signal evidence"}</h2>
            {selectedIc !== null ? <span className={selectedIc >= 0 ? "text-tm-pos" : "text-tm-neg"}>
              <GlossaryTip term="IC OOS">IC</GlossaryTip> {`${selectedIc >= 0 ? "+" : ""}${selectedIc.toFixed(3)}`}
            </span> : null}
          </div>
          {selected ? <>
          <h3 className="mt-2 text-base font-semibold">{getSignalDisplayLabel(selected, locale)}</h3>
          {hasWeightData ? <div className="mt-2 grid grid-cols-3 gap-px border border-tm-rule bg-tm-rule text-center text-xs">
            {[
              [zh ? "线上" : "Live", live?.weight],
              [zh ? "影子" : "Shadow", shadow?.weight],
              [zh ? "保护" : "Guarded", guarded?.weight],
            ].map(([label, value]) => (
              <div key={String(label)} className="bg-tm-bg px-1 py-2">
                <p className="text-tm-muted">{label}</p>
                <p className="mt-1 font-mono text-base text-tm-fg">{typeof value === "number" ? value.toFixed(4) : "—"}</p>
              </div>
            ))}
          </div> : <EvolutionUnavailable locale={locale} message={zh ? "信号权重不可用。" : "Signal weights unavailable."} />}
          {selectedSeries && selectedSeries.points.length > 0 ? (
            <SignalSparkline
              points={selectedSeries.points}
              label={zh ? "近期 IC 观测" : "Recent IC observations"}
              locale={locale}
            />
          ) : null}
          <div className="mt-2 space-y-1 border-t border-tm-rule pt-2 text-xs leading-5">
            {live || shadow ? <div className="flex justify-between gap-2"><span className="text-tm-muted">{zh ? "劣化窗口" : "Degrading windows"}</span><span>{live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows}</span></div> : null}
            {shadow ? <div className="flex justify-between gap-2"><span className="text-tm-muted">{zh ? "晋升累计" : "Promotion streak"}</span><span>{shadow.shadow_streak}/5</span></div> : null}
            <p className="text-tm-muted">{zh ? "最近相关记录：" : "Latest related record: "}{relatedChange ? `${relatedChange.source} · ${formatUtc8DateTime(relatedChange.changed_at)}` : hasChangeData ? (zh ? "已加载账本中未找到" : "Not found in the loaded ledger") : unavailable}</p>
          </div>
          <p className="mt-1 text-xs leading-5 text-tm-muted">{zh ? "事件与前后 IC 仅作同期对照，不代表因果。" : "Events and nearby IC provide context, not causation."}</p>
          </> : <p className="mt-1 text-xs leading-5 text-tm-muted">{zh ? "没有可供对照的信号。权重和校准仍可单独查看。" : "No signal to compare. Weights and calibration can still be viewed separately."}</p>}
        </aside>
      </div>

      <div className="grid grid-cols-1 gap-3 border-b border-tm-rule px-4 py-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:px-6">
        <LifecycleCounts title={zh ? "当前权重状态（信号可重叠）" : "Current weight states (signals can overlap)"}
          entries={[
            [zh ? "线上" : "Live", hasWeightData ? String(liveCount) : unavailable],
            [zh ? "影子" : "Shadow", hasWeightData ? String(shadowCount) : unavailable],
            [zh ? "保护" : "Guarded", hasWeightData ? String(guardedCount) : unavailable],
          ]} />
        <LifecycleCounts title={hasChangeData ? (zh ? `账本事件（已加载 ${changes.length} 条）` : `Ledger events (${changes.length} loaded)`) : (zh ? "账本事件" : "Ledger events")}
          entries={[
            [zh ? "自动晋升" : "Auto-promotions", hasChangeData ? String(promotedCount) : unavailable],
            [zh ? "自动回滚" : "Auto-rollbacks", hasChangeData ? String(rolledBackCount) : unavailable],
          ]} />
      </div>

      {children}

      <details id="evolution-signal-details" className="border-b border-tm-rule">
        <summary className="cursor-pointer px-4 py-3 font-tm-mono text-xs text-tm-muted hover:text-tm-fg lg:px-6">
          {zh ? "全部信号权重与校准明细" : "All signal weights and calibration"}
        </summary>
        <div className="flex min-h-11 items-center gap-3 border-y border-tm-rule px-6 py-1.5">
          <SegmentedTabs
            idBase="evolution-signal-detail"
            ariaLabel={zh ? "信号明细视图" : "Signal detail view"}
            items={[
              { key: "weights", label: zh ? "权重差异" : "Weight deltas" },
              { key: "calibration", label: zh ? "置信校准" : "Calibration" },
            ]}
            active={detailTab}
            onChange={setDetailTab}
          />
        </div>
        <div className="px-6 py-4">
          {detailTab === "weights" ? hasWeightData ? <WeightDeltaTable weights={weights} locale={locale} /> : <EvolutionUnavailable locale={locale} /> : null}
          {detailTab === "calibration" ? calibration ? <ReliabilityChart calibration={calibration} locale={locale} /> : <EvolutionUnavailable locale={locale} /> : null}
        </div>
      </details>

    </section>
  );
}

function LifecycleCounts({ title, entries }: { title: string; entries: readonly [string, string][] }) {
  return (
    <section className="min-w-0 border border-tm-rule px-3 py-2">
      <h2 className="font-tm-mono text-xs font-semibold text-tm-fg">{title}</h2>
      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2">
            <dt className="text-tm-muted">{label}</dt>
            <dd className="font-tm-mono text-sm tabular-nums text-tm-fg">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function SignalSparkline({ points, label, locale }: { readonly points: readonly { computed_at: string; ic: number }[]; readonly label: string; readonly locale: Locale }) {
  const ordered = [...points].sort((a, b) => a.computed_at.localeCompare(b.computed_at));
  const values = ordered.map((point) => point.ic);
  const min = Math.min(...values, -0.01);
  const max = Math.max(...values, 0.01);
  const range = Math.max(max - min, 0.001);
  const coordinates = ordered.map((point, index) => {
    const x = 8 + (index / Math.max(points.length - 1, 1)) * 284;
    const y = 78 - ((point.ic - min) / range) * 62;
    return { x, y };
  });
  const enough = hasEnoughIcObservations(points.length);
  const zeroY = 78 - ((0 - min) / range) * 62;
  return (
    <div className="mt-3 border border-tm-rule bg-tm-bg px-3 py-2">
      <div className="flex items-center justify-between text-xs text-tm-muted"><span>{label}</span><span>{locale === "zh" ? `${points.length} 个观测` : `${points.length} observations`}</span></div>
      <svg viewBox="0 0 300 86" className="mt-2 h-[96px] w-full" role="img" aria-label={label}>
        <line x1="8" x2="292" y1={zeroY} y2={zeroY} stroke="currentColor" className="text-tm-rule" strokeDasharray="3 3" />
        {enough ? <polyline points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")} fill="none" stroke="currentColor" className="text-tm-pos" strokeWidth="2" />
          : coordinates.map(({ x, y }, i) => <circle key={i} cx={x} cy={y} r="3" fill="currentColor" className="text-tm-pos" />)}
      </svg>
      {!enough ? <p className="mt-1 text-xs text-tm-warn">{locale === "zh" ? `观测不足（${points.length} 个点），不构成趋势` : `Too few observations (${points.length}); not a trend`}</p> : null}
    </div>
  );
}
