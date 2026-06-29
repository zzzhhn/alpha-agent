"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { classifyFactorTier } from "@/lib/factor-tier";
import type { FactorBacktestResponse } from "@/lib/types";

/**
 * BacktestVerdictHeadline — the decision-first banner above the metric strip
 * (ALPHACORE design, backtest block lines 241-244). It answers the one
 * question the user asked for at a glance: is this a REAL factor, or an
 * OVERFIT artifact?
 *
 * The verdict is DERIVED from the run's own stats, never hand-labelled:
 *   1. overfit_flag (oos_decay > 0.5) is the dominant signal — if the in-sample
 *      Sharpe collapses out-of-sample, that's flagged first, because no amount
 *      of significant α matters if it doesn't survive the test slice.
 *   2. otherwise the canonical factor tier (classifyFactorTier on α-p + β):
 *      PURE ALPHA → real, LEVERED → market-levered, MARGINAL → weak, NOISE.
 *   3. missing α-attribution → UNDETERMINED (honest "—", no fabricated verdict).
 */

type VerdictTone = "pos" | "info" | "warn" | "bad" | "muted";
type VerdictCategory =
  | "real"
  | "levered"
  | "marginal"
  | "noise"
  | "overfit"
  | "unknown";

const OVERFIT_DECAY = 0.5;

const TONE: Record<VerdictTone, { bar: string; badge: string; bg: string }> = {
  pos: { bar: "border-l-tm-pos", badge: "border-tm-pos text-tm-pos", bg: "bg-tm-pos/5" },
  info: { bar: "border-l-tm-accent", badge: "border-tm-accent text-tm-accent", bg: "bg-tm-accent/5" },
  warn: { bar: "border-l-tm-warn", badge: "border-tm-warn text-tm-warn", bg: "bg-tm-warn/5" },
  bad: { bar: "border-l-tm-neg", badge: "border-tm-neg text-tm-neg", bg: "bg-tm-neg/5" },
  muted: { bar: "border-l-tm-rule-2", badge: "border-tm-rule-2 text-tm-muted", bg: "bg-tm-bg-2" },
};

const CATEGORY_TONE: Record<VerdictCategory, VerdictTone> = {
  real: "pos",
  levered: "info",
  marginal: "warn",
  noise: "bad",
  overfit: "bad",
  unknown: "muted",
};

function deriveCategory(raw: FactorBacktestResponse): VerdictCategory {
  const decay = raw.oos_decay;
  const overfit =
    raw.overfit_flag === true ||
    (decay != null && Number.isFinite(decay) && decay > OVERFIT_DECAY);
  if (overfit) return "overfit";

  const tier = classifyFactorTier(raw.alpha_pvalue, raw.beta_market);
  switch (tier.label) {
    case "PURE ALPHA":
      return "real";
    case "LEVERED ALPHA":
      return "levered";
    case "MARGINAL":
      return "marginal";
    case "NOISE":
      return "noise";
    default:
      return "unknown";
  }
}

function fmtSharpe(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2);
}
function fmtP(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(3);
}
function fmtBeta(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2);
}
function fmtDecay(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(0)}%`;
}

function Kpi({
  label,
  value,
  valueClass = "text-tm-fg",
}: {
  readonly label: string;
  readonly value: string;
  readonly valueClass?: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1 text-tm-muted">
      {label}
      <span className={`font-mono tabular-nums ${valueClass}`}>{value}</span>
    </span>
  );
}

export function BacktestVerdictHeadline({
  raw,
}: {
  readonly raw: FactorBacktestResponse;
}) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);

  const category = deriveCategory(raw);
  const tone = TONE[CATEGORY_TONE[category]];
  const label = tk(`backtest.verdict.${category}.label`);
  const msg = tk(`backtest.verdict.${category}.msg`);

  const testSharpe = raw.test_metrics?.sharpe;
  const alphaP = raw.alpha_pvalue;
  const beta = raw.beta_market;
  const decay = raw.oos_decay;

  return (
    <section
      className={`border border-l-[3px] border-tm-rule ${tone.bar} ${tone.bg} px-4 py-3`}
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="font-tm-mono text-[9px] font-semibold tracking-[0.16em] text-tm-muted">
          {tk("backtest.verdict.heading")}
        </span>
        <span
          className={`border px-2 py-0.5 font-tm-mono text-[11px] font-bold tracking-[0.04em] ${tone.badge}`}
        >
          {label}
        </span>
      </div>

      <p className="mt-1.5 max-w-3xl text-[13px] leading-snug text-tm-fg">
        {msg}
      </p>

      <div className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 font-tm-mono text-[11.5px]">
        <Kpi
          label={tk("backtest.verdict.kpiTestSharpe")}
          value={fmtSharpe(testSharpe)}
          valueClass={
            testSharpe != null && testSharpe >= 1
              ? "text-tm-pos"
              : "text-tm-fg"
          }
        />
        <Kpi
          label={tk("backtest.verdict.kpiAlphaP")}
          value={fmtP(alphaP)}
          valueClass={
            alphaP != null && alphaP < 0.05 ? "text-tm-pos" : "text-tm-fg"
          }
        />
        <Kpi label={tk("backtest.verdict.kpiBeta")} value={fmtBeta(beta)} />
        <Kpi
          label={tk("backtest.verdict.kpiDecay")}
          value={fmtDecay(decay)}
          valueClass={
            decay != null && decay > OVERFIT_DECAY
              ? "text-tm-neg"
              : "text-tm-pos"
          }
        />
      </div>
    </section>
  );
}
