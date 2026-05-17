"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { RatingCard } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

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

// Display-label overrides for radar vertex names.
// Backend signal names stay stable (`macro`, `political_impact`); only the
// rendered label changes so users can tell "Macro (Vol)" apart from political
// signals. i18n key takes precedence; falls back to this map; falls back to
// the raw signal name.
const SIGNAL_DISPLAY_LABEL: Record<string, Record<Locale, string>> = {
  macro: { zh: "宏观 (波动率)", en: "Macro (Vol)" },
  political_impact: { zh: "政治", en: "Political" },
};

function displayName(signalName: string, locale: Locale): string {
  const key = `attribution.signal_label_${signalName}`;
  const translated = t(locale, key as Parameters<typeof t>[1]);
  // t() returns the key itself when missing; treat that as a miss.
  if (translated !== key) return translated;
  const fallback = SIGNAL_DISPLAY_LABEL[signalName]?.[locale];
  return fallback ?? signalName;
}

export default function AttributionRadar({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const data = card.breakdown.map((b) => ({
    signal: displayName(b.signal, locale),
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
