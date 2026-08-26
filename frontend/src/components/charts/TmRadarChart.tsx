"use client";

import dynamic from "next/dynamic";
import { TM_CHART_CSS, TM_CHART_TYPOGRAPHY } from "./chartTokens";

const RadarChart = dynamic(() => import("recharts").then((module) => module.RadarChart), { ssr: false });
const Radar = dynamic(() => import("recharts").then((module) => module.Radar), { ssr: false });
const PolarGrid = dynamic(() => import("recharts").then((module) => module.PolarGrid), { ssr: false });
const PolarAngleAxis = dynamic(() => import("recharts").then((module) => module.PolarAngleAxis), { ssr: false });
const PolarRadiusAxis = dynamic(() => import("recharts").then((module) => module.PolarRadiusAxis), { ssr: false });
const Tooltip = dynamic(() => import("recharts").then((module) => module.Tooltip), { ssr: false });
const ResponsiveContainer = dynamic(() => import("recharts").then((module) => module.ResponsiveContainer), { ssr: false });

export type TmRadarDatum = {
  readonly label: string;
  readonly positive: number;
  readonly negative: number;
  readonly raw: number;
};

export function TmRadarChart({
  data,
  positiveLabel,
  negativeLabel,
  summary,
  ariaLabel,
  maximum = 3,
}: {
  readonly data: readonly TmRadarDatum[];
  readonly positiveLabel: string;
  readonly negativeLabel: string;
  readonly summary: string;
  readonly ariaLabel: string;
  readonly maximum?: number;
}) {
  return (
    <figure className="w-full text-tm-fg-2">
      <div className="h-[280px] w-full" role="img" aria-label={ariaLabel}>
        <ResponsiveContainer>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke={TM_CHART_CSS.gridStrong} strokeOpacity={0.8} />
            <PolarAngleAxis
              dataKey="label"
              tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: "currentColor" }}
            />
            <PolarRadiusAxis
              domain={[0, maximum]}
              tickCount={4}
              tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: "currentColor" }}
              angle={90}
              tickFormatter={(value: number) => (value === 0 ? "0" : `${value}σ`)}
            />
            <Radar
              name={positiveLabel}
              dataKey="positive"
              stroke={TM_CHART_CSS.information}
              fill={TM_CHART_CSS.information}
              fillOpacity={0.4}
            />
            <Radar
              name={negativeLabel}
              dataKey="negative"
              stroke={TM_CHART_CSS.negative}
              fill={TM_CHART_CSS.negative}
              fillOpacity={0.32}
            />
            <Tooltip
              contentStyle={{
                background: TM_CHART_CSS.surface,
                border: `1px solid ${TM_CHART_CSS.gridStrong}`,
                borderRadius: 0,
                color: TM_CHART_CSS.foreground,
                fontSize: TM_CHART_TYPOGRAPHY.tooltip,
              }}
              formatter={(_value, _name, item) => {
                const payload = (item as unknown as { payload?: { raw?: number } } | undefined)?.payload;
                const raw = payload?.raw ?? 0;
                return [`${raw >= 0 ? "+" : ""}${raw.toFixed(2)}σ`, "z"];
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-center text-xs leading-5 text-tm-muted">{summary}</figcaption>
    </figure>
  );
}
