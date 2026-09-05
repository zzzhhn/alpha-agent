"use client";

import { TM_CHART_CSS, TM_CHART_TYPOGRAPHY } from "./chartTokens";
import { TmTooltip } from "@/components/tm/TmTooltip";

export type TmRadarDatum = {
  readonly label: string;
  readonly positive: number;
  readonly negative: number;
  readonly raw: number | null;
};

export function TmRadarChart({
  data, positiveLabel, negativeLabel, summary, ariaLabel,
  unavailableLabel = "N/A", maximum = 3,
}: {
  readonly data: readonly TmRadarDatum[];
  readonly positiveLabel: string;
  readonly negativeLabel: string;
  readonly summary: string;
  readonly ariaLabel: string;
  readonly unavailableLabel?: string;
  readonly maximum?: number;
}) {
  const point = (index: number, radius: number) => {
    const angle = (index / data.length) * 2 * Math.PI - Math.PI / 2;
    return [180 + Math.cos(angle) * radius, 140 + Math.sin(angle) * radius];
  };
  const complete = data.length > 0 && data.every((d) => d.raw !== null);
  const format = (raw: number | null) => raw === null
    ? unavailableLabel : `${raw >= 0 ? "+" : ""}${raw.toFixed(2)}σ`;
  const series = [
    { key: "positive" as const, label: positiveLabel, color: TM_CHART_CSS.information },
    { key: "negative" as const, label: negativeLabel, color: TM_CHART_CSS.negative },
  ];
  return (
    <figure className="w-full text-tm-fg-2">
      <svg viewBox="0 0 360 280" role="img" aria-label={ariaLabel} className="mx-auto block w-full max-w-[420px]">
        <desc>{data.map((d) => `${d.label}: ${format(d.raw)}`).join("; ")}</desc>
        {[1, 2, 3].map((step) => (
          <polygon key={step} points={data.map((_, i) => point(i, step * 30).join(",")).join(" ")}
            fill="none" stroke={TM_CHART_CSS.gridStrong} strokeDasharray="2 4" />
        ))}
        {data.map((datum, i) => {
          const end = point(i, 90);
          const label = point(i, 116);
          return (
            <g key={datum.label}>
              <line x1={180} y1={140} x2={end[0]} y2={end[1]} stroke={TM_CHART_CSS.gridStrong}
                strokeDasharray={datum.raw === null ? "3 4" : undefined} />
              <text x={label[0]} y={label[1]} textAnchor="middle" dominantBaseline="middle"
                fill={datum.raw === null ? TM_CHART_CSS.muted : TM_CHART_CSS.foreground} fontSize={TM_CHART_TYPOGRAPHY.svgLabel}>
                {datum.label}{datum.raw === null ? " *" : ""}
              </text>
            </g>
          );
        })}
        {series.map((s) => (
          <g key={s.key} stroke={s.color} strokeWidth={2}>
            {complete ? (
              <polygon points={data.map((d, i) => point(i, Math.min(d[s.key], maximum) / maximum * 90).join(",")).join(" ")}
                fill={s.color} fillOpacity={0.15} />
            ) : null}
            {data.map((d, i) => {
              if (d.raw === null || d[s.key] <= 0) return null;
              const [x, y] = point(i, Math.min(d[s.key], maximum) / maximum * 90);
              return <g key={d.label}>
                {!complete ? <line x1={180} y1={140} x2={x} y2={y} /> : null}
                <circle cx={x} cy={y} r={3} fill={s.color} />
              </g>;
            })}
          </g>
        ))}
        <text x={188} y={133} fill={TM_CHART_CSS.muted} fontSize={TM_CHART_TYPOGRAPHY.svgLabel}>0</text>
      </svg>
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
        {series.map((s) => <span key={s.key} className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4" style={{ background: s.color }} aria-hidden="true" />{s.label}
        </span>)}
        <span className="text-tm-muted">0–{maximum}σ</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 border-t border-tm-rule pt-2 text-xs">
        {data.map((d) => <div key={d.label} className="flex items-center justify-between gap-2">
          <dt><TmTooltip content={`${d.label}: ${format(d.raw)}`} ariaLabel={d.label}>{d.label}</TmTooltip></dt>
          <dd className={d.raw === null ? "text-tm-muted" : "font-tm-mono text-tm-fg"}>{format(d.raw)}</dd>
        </div>)}
      </dl>
      <figcaption className="mt-3 text-xs leading-5 text-tm-muted">{summary}</figcaption>
    </figure>
  );
}
