"use client";

import clsx from "clsx";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import type { Locale } from "@/lib/i18n";
import type { EvolutionHealth, HealthTone, SubVerdict } from "@/lib/evolution-health";

// Tone → color + glyph + verdict word. 'action' (pending decisions) and
// 'warn' (a real concern) are the two that should pull the eye; good/neutral
// recede so the strip surfaces what needs attention (rules 1/2/10).
const TONE_META: Record<
  HealthTone,
  { color: string; glyph: string; zh: string; en: string }
> = {
  good: { color: "text-tm-pos", glyph: "✓", zh: "健康", en: "Healthy" },
  warn: { color: "text-tm-warn", glyph: "⚠", zh: "注意", en: "Caution" },
  action: { color: "text-tm-accent", glyph: "→", zh: "待处理", en: "Action" },
  neutral: { color: "text-tm-fg-2", glyph: "—", zh: "正常", en: "Normal" },
  na: { color: "text-tm-muted", glyph: "·", zh: "无数据", en: "N/A" },
};

function num(f: SubVerdict["facts"], key: string): number | null {
  const v = f[key];
  return typeof v === "number" ? v : null;
}

export default function EvolutionHealthStrip({
  health,
  locale,
}: {
  health: EvolutionHealth;
  locale: Locale;
}) {
  const zh = locale === "zh";

  // Overall headline: a real concern (warn) outranks a pending decision
  // (action) outranks all-clear. Drives the pane meta one-liner.
  const tones = [
    health.calibration.tone,
    health.ic.tone,
    health.weights.tone,
    health.proposals.tone,
  ];
  const overall: HealthTone = tones.includes("warn")
    ? "warn"
    : tones.includes("action")
      ? "action"
      : tones.includes("good")
        ? "good"
        : "neutral";

  // ── Per-cell readout builders (localized) ──────────────────────────────
  const cal = health.calibration;
  const calReadout = (() => {
    if (cal.tone === "na") return zh ? "无校准数据" : "no calibration data";
    if (cal.facts.applied === false) {
      const n = num(cal.facts, "nPairs") ?? 0;
      return zh ? `累积中 (${n}/50 对)` : `accumulating (${n}/50 pairs)`;
    }
    const brier = num(cal.facts, "brier");
    const parts: string[] = [];
    if (brier !== null) {
      const noSkill = cal.facts.worseThanGuess
        ? zh
          ? " ≈ 瞎猜基线"
          : " ≈ no-skill"
        : "";
      parts.push(`Brier ${brier.toFixed(2)}${noSkill}`);
    }
    if (cal.facts.overconfident) parts.push(zh ? "高端过度自信" : "overconfident high-end");
    const n = num(cal.facts, "nPairs");
    if (n !== null) parts.push(zh ? `${n} 对` : `${n} pairs`);
    return parts.join(" · ");
  })();

  const ic = health.ic;
  const icReadout = (() => {
    if (ic.tone === "na") return zh ? "无 IC 数据" : "no IC data";
    const pos = num(ic.facts, "pos") ?? 0;
    const total = num(ic.facts, "total") ?? 0;
    const strongest = ic.facts.strongestName;
    const strongestIc = num(ic.facts, "strongestIc");
    const head = zh ? `${pos}/${total} 正 IC` : `${pos}/${total} positive IC`;
    if (typeof strongest === "string" && strongest && strongestIc !== null) {
      const label = getSignalDisplayLabel(strongest, locale);
      const sign = strongestIc >= 0 ? "+" : "";
      return zh
        ? `${head} · 最强 ${label} ${sign}${strongestIc.toFixed(2)}`
        : `${head} · top ${label} ${sign}${strongestIc.toFixed(2)}`;
    }
    return head;
  })();

  const w = health.weights;
  const wReadout = (() => {
    if (w.tone === "na") return zh ? "无权重数据" : "no weight data";
    const signals = num(w.facts, "signals") ?? 0;
    const shadow = num(w.facts, "shadow") ?? 0;
    const degrading = num(w.facts, "degrading") ?? 0;
    const near = num(w.facts, "nearPromotion") ?? 0;
    const parts = zh
      ? [`${signals} 信号`, `${shadow} 候选累积`, `${degrading} 劣化`]
      : [`${signals} signals`, `${shadow} accumulating`, `${degrading} degrading`];
    if (near > 0) parts.push(zh ? `${near} 近晋升` : `${near} near promotion`);
    return parts.join(" · ");
  })();

  const pr = health.proposals;
  const prReadout = (() => {
    if (pr.tone === "na") return zh ? "无提议数据" : "no proposal data";
    const pending = num(pr.facts, "pending") ?? 0;
    if (pending > 0) return zh ? `${pending} 条待审批` : `${pending} awaiting review`;
    return zh ? "无待审 · proposer 休眠" : "none pending · proposer dormant";
  })();

  const cells: { label: string; v: SubVerdict; readout: string }[] = [
    { label: zh ? "校准可信度" : "Calibration", v: cal, readout: calReadout },
    { label: zh ? "IC 有效性" : "Signal IC", v: ic, readout: icReadout },
    { label: zh ? "权重自调节" : "Adaptive weights", v: w, readout: wReadout },
    { label: zh ? "待审提议" : "Proposals", v: pr, readout: prReadout },
  ];

  const overallMeta = TONE_META[overall];

  return (
    <div className="border-b border-tm-rule bg-tm-bg-2/40">
      <div className="flex items-center justify-between px-4 pt-3">
        <h2 className="font-tm-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
          {zh ? "自进化健康度" : "SELF-EVOLUTION HEALTH"}
        </h2>
        <span className={clsx("font-tm-mono text-[10px]", overallMeta.color)}>
          {overallMeta.glyph} {zh ? overallMeta.zh : overallMeta.en}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 px-4 py-3 sm:grid-cols-2 lg:grid-cols-4">
        {cells.map(({ label, v, readout }) => {
          const meta = TONE_META[v.tone];
          return (
            <div
              key={label}
              className="rounded border border-tm-rule bg-tm-bg px-2.5 py-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-tm-mono text-[10px] text-tm-fg-2">
                  {label}
                </span>
                <span className={clsx("font-tm-mono text-[10px]", meta.color)}>
                  {meta.glyph} {zh ? meta.zh : meta.en}
                </span>
              </div>
              <p className="mt-1 font-tm-mono text-[10px] leading-snug text-tm-muted">
                {readout}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
