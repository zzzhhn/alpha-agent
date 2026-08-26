"use client";

import type { RatingCard, BreakdownEntry } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { useFactorMode } from "@/hooks/useFactorMode";
import { applyFactorModeToCard } from "@/lib/picks-mode";
import { useWeightsOverride } from "@/hooks/useWeightsOverride";
import { applyWeightsToCard } from "@/lib/weights-override";
import { TmRadarChart } from "@/components/charts/TmRadarChart";

// Fixed radar scale [0, 3] sigma so visualization stays stable across tickers
// instead of auto-scaling to the largest z in the breakdown.
const RADAR_MAX = 3;

// A signal earns a radar axis only when it is backed by real data. Phantom
// axes (no-data / structurally-disabled signals) all sit at the center and
// turn the polygon into a lopsided "needle", so they are dropped:
//   - weight 0  -> structurally disabled (calendar / political / geopolitical)
//   - z null    -> no data (e.g. insider with no filings in 30d)
//   - error + a zeroed reading -> fetch failed (e.g. premarket "no data")
// A real signal that happens to read neutral (z=0, no error, weight>0, e.g.
// news with balanced headlines) is kept: it is a genuine measurement.
function isRealDataAxis(b: BreakdownEntry): boolean {
  const w = b.weight_effective ?? b.weight ?? 0;
  if (w <= 0) return false;
  if (b.z === null || b.z === undefined) return false;
  if (b.error && Math.abs(b.z) < 1e-9) return false;
  return true;
}

export default function AttributionRadar({ card }: { card: RatingCard }) {
  const { locale } = useLocale();
  const [factorMode] = useFactorMode();
  const weights = useWeightsOverride();
  // Apply mode swap so the factor petal + composite footer reflect the
  // active toggle. Same useFactorMode hook subscribes to localStorage so a
  // flip on /picks (or via AttributionTable's pill) re-renders this radar.
  // Then apply the personal weight override (factor-mode first so the
  // recompute uses the moded z's); zeroing a signal's weight also drops its
  // spoke via isRealDataAxis (weight_effective -> 0).
  const modedCard = (() => {
    const c = applyFactorModeToCard(card, factorMode);
    return weights ? applyWeightsToCard(c, weights) : c;
  })();

  // Split each real signal's z into a positive and a negative magnitude on
  // the same axis. Two coloured Radar series (blue = bullish, red = bearish)
  // mean every real signal gets a spoke regardless of sign, so a bearish-
  // tilted stock no longer collapses to a needle, and direction stays honest
  // via colour instead of being clamped invisibly to the center.
  const data = modedCard.breakdown.filter(isRealDataAxis).map((b) => {
    const z = b.z ?? 0;
    return {
      label: getSignalDisplayLabel(b.signal, locale),
      positive: z > 0 ? Math.min(z, RADAR_MAX) : 0,
      negative: z < 0 ? Math.min(-z, RADAR_MAX) : 0,
      raw: z,
    };
  });
  const composite = modedCard.composite_score ?? 0;

  if (data.length === 0) {
    return (
      <div
        style={{ width: "100%", height: 280 }}
        className="flex items-center justify-center text-xs text-tm-muted"
      >
        {t(locale, "radar.no_data")}
      </div>
    );
  }

  return (
    <TmRadarChart
      data={data}
      positiveLabel={t(locale, "radar.bullish")}
      negativeLabel={t(locale, "radar.bearish")}
      maximum={RADAR_MAX}
      ariaLabel={locale === "zh" ? "股票信号归因雷达图" : "Stock signal attribution radar chart"}
      summary={`composite ${composite >= 0 ? "+" : ""}${composite.toFixed(2)}σ`}
    />
  );
}
