"use client";

import dynamic from "next/dynamic";
import type { RatingCard } from "@/lib/api/picks";

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
const ResponsiveContainer = dynamic(
  () => import("recharts").then((m) => m.ResponsiveContainer),
  { ssr: false },
);

export default function AttributionRadar({ card }: { card: RatingCard }) {
  const data = card.breakdown.map((b) => ({
    signal: b.signal,
    z: Math.abs(b.z),
  }));

  // Fixed-height parent required — ResponsiveContainer reads offsetWidth;
  // without it the container collapses to 0 in grid/flex parents (CLAUDE.md memory).
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <RadarChart data={data}>
          <PolarGrid stroke="#3f3f46" />
          <PolarAngleAxis
            dataKey="signal"
            tick={{ fontSize: 10, fill: "#a1a1aa" }}
          />
          <Radar
            dataKey="z"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>
      <div className="text-center text-xs text-zinc-500 mt-1">
        composite {card.composite_score >= 0 ? "+" : ""}
        {card.composite_score.toFixed(2)}σ
      </div>
    </div>
  );
}
