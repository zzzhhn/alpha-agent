"use client";

import dynamic from "next/dynamic";
import type { RatingCard, BreakdownEntry } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { useFactorMode } from "@/hooks/useFactorMode";
import { applyFactorModeToCard } from "@/lib/picks-mode";

// Dynamic imports keep Recharts (~150KB gzip) out of the initial server chunk.
// Per CLAUDE.md memory: wrap ResponsiveContainer in a fixed-height div.
const RadarChart = dynamic(
  () => import("recharts").then((m) => m.RadarChart),
  { ssr: false },
);
const Radar = dynamic(() => import("recharts").then((m) => m.Radar), {
  ssr: false,
});
const PolarGrid = dynamic(
  () => import("recharts").then((m) => m.PolarGrid),
  { ssr: false },
);
const PolarAngleAxis = dynamic(
  () => import("recharts").then((m) => m.PolarAngleAxis),
  { ssr: false },
);
const PolarRadiusAxis = dynamic(
  () => import("recharts").then((m) => m.PolarRadiusAxis),
  { ssr: false },
);
const Tooltip = dynamic(
  () => import("recharts").then((m) => m.Tooltip),
  { ssr: false },
);
const ResponsiveContainer = dynamic(
  () => import("recharts").then((m) => m.ResponsiveContainer),
  { ssr: false },
);

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
  // Apply mode swap so the factor petal + composite footer reflect the
  // active toggle. Same useFactorMode hook subscribes to localStorage so a
  // flip on /picks (or via AttributionTable's pill) re-renders this radar.
  const modedCard = applyFactorModeToCard(card, factorMode);

  // Split each real signal's z into a positive and a negative magnitude on
  // the same axis. Two coloured Radar series (blue = bullish, red = bearish)
  // mean every real signal gets a spoke regardless of sign, so a bearish-
  // tilted stock no longer collapses to a needle, and direction stays honest
  // via colour instead of being clamped invisibly to the center.
  const data = modedCard.breakdown.filter(isRealDataAxis).map((b) => {
    const z = b.z ?? 0;
    return {
      signal: getSignalDisplayLabel(b.signal, locale),
      pos: z > 0 ? Math.min(z, RADAR_MAX) : 0,
      neg: z < 0 ? Math.min(-z, RADAR_MAX) : 0,
      z_raw: z,
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

  // Fixed-height parent required — ResponsiveContainer reads offsetWidth;
  // without it the container collapses to 0 in grid/flex parents (CLAUDE.md memory).
  return (
    <div style={{ width: "100%", height: 280 }} className="text-tm-fg-2">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="75%">
          <PolarGrid stroke="#9ca3af" strokeOpacity={0.4} />
          <PolarAngleAxis
            dataKey="signal"
            tick={{ fontSize: 10, fill: "currentColor" }}
          />
          <PolarRadiusAxis
            domain={[0, RADAR_MAX]}
            tickCount={4}
            tick={{ fontSize: 9, fill: "currentColor" }}
            angle={90}
            tickFormatter={(v: number) => (v === 0 ? "0" : `${v}σ`)}
          />
          {/* bullish magnitude (blue) */}
          <Radar
            name={t(locale, "radar.bullish")}
            dataKey="pos"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.4}
          />
          {/* bearish magnitude (red) */}
          <Radar
            name={t(locale, "radar.bearish")}
            dataKey="neg"
            stroke="#dc2626"
            fill="#dc2626"
            fillOpacity={0.32}
          />
          <Tooltip
            contentStyle={{
              background: "rgba(15, 23, 42, 0.92)",
              border: "1px solid #475569",
              borderRadius: 4,
              color: "#e2e8f0",
              fontSize: 11,
            }}
            formatter={(_value, _name, item) => {
              const payload = (item as unknown as { payload?: { z_raw?: number } } | undefined)?.payload;
              const raw = payload?.z_raw ?? 0;
              const sign = raw >= 0 ? "+" : "";
              return [`${sign}${raw.toFixed(2)}σ`, "z"];
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
      <div className="text-center text-xs text-tm-muted mt-1">
        composite {composite >= 0 ? "+" : ""}
        {composite.toFixed(2)}σ
      </div>
    </div>
  );
}
