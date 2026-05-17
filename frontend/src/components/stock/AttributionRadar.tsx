"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { RatingCard } from "@/lib/api/picks";
import { getLocaleFromStorage, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";

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
// instead of auto-scaling to the largest z in the breakdown (which collapses
// a typical card with 1-2 strong signals into a tiny shape near the center).
const RADAR_MAX = 3;

// Negative z values are clamped to 0 on the radar. Radar charts naturally
// cannot express negative radii without offset tricks that confuse readers;
// negative signals are still fully visible in the AttributionTable column.
function clampToRadar(z: number): number {
  if (z <= 0) return 0;
  return Math.min(z, RADAR_MAX);
}

export default function AttributionRadar({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const data = card.breakdown.map((b) => ({
    signal: getSignalDisplayLabel(b.signal, locale),
    z_visible: clampToRadar(b.z ?? 0),
    z_raw: b.z ?? 0,
  }));
  const composite = card.composite_score ?? 0;

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
          <Radar
            dataKey="z_visible"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.45}
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
