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
    z: Math.abs(b.z ?? 0),
  }));
  const composite = card.composite_score ?? 0;

  // Fixed-height parent required — ResponsiveContainer reads offsetWidth;
  // without it the container collapses to 0 in grid/flex parents (CLAUDE.md memory).
  // Colors: mid-tone gray for grid/labels stays legible across both themes.
  // Accent stroke is blue-500 which holds contrast on both light cream + dark bg.
  return (
    <div style={{ width: "100%", height: 280 }} className="text-tm-fg-2">
      <ResponsiveContainer>
        <RadarChart data={data}>
          <PolarGrid stroke="#9ca3af" strokeOpacity={0.4} />
          <PolarAngleAxis
            dataKey="signal"
            tick={{ fontSize: 10, fill: "currentColor" }}
          />
          <Radar
            dataKey="z"
            stroke="#3b82f6"
            fill="#3b82f6"
            fillOpacity={0.25}
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
