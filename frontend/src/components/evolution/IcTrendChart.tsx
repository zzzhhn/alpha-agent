"use client";

import { useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import type { IcTrendSeries, IcAnnotation } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { nativeHorizon } from "@/lib/signal-horizons";
import { formatIcAnnotation } from "@/lib/ic-annotation-format";

interface IcTrendChartProps {
  readonly series: IcTrendSeries[];
  readonly locale: Locale;
  // Traceability overlay: material IC moves to mark + explain on hover.
  readonly annotations?: IcAnnotation[];
}

// One color per signal, cycling through tm vars then fallback hex values.
const SIGNAL_COLORS = [
  "var(--tm-accent)",
  "var(--tm-info)",
  "var(--tm-pos, #10b981)",
  "var(--tm-warn, #f59e0b)",
  "var(--tm-neg, #f87171)",
  "#a78bfa",
  "#38bdf8",
];

function shortDate(iso: string): string {
  // "2025-03-15T00:00:00" → "03-15"
  return iso.slice(5, 10);
}

interface MergedRow {
  readonly date: string;
  // Full ISO timestamp of the row, so annotation markers/tooltip can match
  // precisely even when two points share an MM-DD label.
  readonly _ts: string;
  [signalName: string]: number | string;
}

function mergeIcSeries(series: IcTrendSeries[]): MergedRow[] {
  // Collect all unique timestamps across all signals.
  const dateSet = new Set<string>();
  for (const s of series) {
    for (const p of s.points) {
      dateSet.add(p.computed_at);
    }
  }
  const sortedDates = Array.from(dateSet).sort();
  if (sortedDates.length === 0) return [];

  // Build per-signal lookup maps.
  const maps = series.map((s) => {
    const m = new Map<string, number>();
    for (const p of s.points) {
      m.set(p.computed_at, p.ic);
    }
    return m;
  });

  return sortedDates.map((date) => {
    const row: MergedRow = { date: shortDate(date), _ts: date };
    series.forEach((s, i) => {
      const v = maps[i].get(date);
      if (v !== undefined) {
        row[s.signal_name] = v;
      }
    });
    return row;
  });
}

// Diamond marker drawn on a line at an annotated (signal, day) point. Recharts
// calls the Line `dot` render fn for every point; we draw only where an
// annotation exists and render an empty group otherwise.
function annotationDot(
  signal: string,
  annByKey: Map<string, IcAnnotation>,
  // recharts dot render props (loosely typed — the lib's types are partial).
  props: { cx?: number; cy?: number; payload?: MergedRow; stroke?: string },
) {
  const { cx, cy, payload, stroke } = props;
  const ts = payload?._ts;
  const ann = ts ? annByKey.get(`${signal}@${ts}`) : undefined;
  const key = `${signal}-${ts ?? "x"}`;
  if (ann === undefined || cx === undefined || cy === undefined) {
    return <g key={key} />;
  }
  // Sign-flips (crossing zero) get a hollow ring on top to stand out more.
  return (
    <g key={key}>
      <path
        d={`M ${cx} ${cy - 4} L ${cx + 4} ${cy} L ${cx} ${cy + 4} L ${cx - 4} ${cy} Z`}
        fill={stroke ?? "var(--tm-fg)"}
        stroke="var(--tm-bg)"
        strokeWidth={1}
      />
      {ann.sign_flip ? (
        <circle
          cx={cx}
          cy={cy}
          r={6.5}
          fill="none"
          stroke={stroke ?? "var(--tm-fg)"}
          strokeWidth={1}
          opacity={0.7}
        />
      ) : null}
    </g>
  );
}

// Tooltip that augments the default IC readout with any traceability
// annotations for the hovered day — the "hover card" carrying the grounded
// change narrative.
function IcTooltip(props: {
  active?: boolean;
  payload?: Array<{ payload?: MergedRow }>;
  annByTs: Map<string, IcAnnotation[]>;
  locale: Locale;
}) {
  const { active, payload, annByTs, locale } = props;
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const anns = annByTs.get(row._ts) ?? [];

  return (
    <div className="rounded border border-tm-rule bg-tm-bg-2 px-2.5 py-2 font-tm-mono text-[11px] text-tm-fg shadow-lg shadow-black/30">
      <div className="mb-1 text-tm-muted">{row.date}</div>
      {anns.length === 0 ? (
        <div className="text-[10px] text-tm-muted">
          {t(locale, "evolution.trace.no_change_here")}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {anns.map((ann) => {
            const f = formatIcAnnotation(ann, locale);
            const tone = ann.sign_flip
              ? "text-tm-warn"
              : (ann.delta ?? 0) >= 0
                ? "text-tm-pos"
                : "text-tm-neg";
            return (
              <div key={ann.signal_name} className="max-w-[260px]">
                <div className={tone}>{f.headline}</div>
                {f.flipNote ? (
                  <div className="text-[10px] text-tm-warn">{f.flipNote}</div>
                ) : null}
                <div className="mt-0.5 text-[10px] text-tm-muted">
                  {f.coOccurring.length > 0
                    ? f.coOccurring.join(" · ")
                    : f.noCause}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function IcTrendChart({ series, locale, annotations }: IcTrendChartProps) {
  const hasData = series.length > 0 && series.some((s) => s.points.length > 0);

  const merged = useMemo(() => mergeIcSeries(series), [series]);

  // Index annotations both per (signal, day) for the dots and per day for the
  // tooltip card.
  const { annByKey, annByTs } = useMemo(() => {
    const byKey = new Map<string, IcAnnotation>();
    const byTs = new Map<string, IcAnnotation[]>();
    for (const a of annotations ?? []) {
      byKey.set(`${a.signal_name}@${a.as_of}`, a);
      const list = byTs.get(a.as_of) ?? [];
      list.push(a);
      byTs.set(a.as_of, list);
    }
    return { annByKey: byKey, annByTs: byTs };
  }, [annotations]);

  if (!hasData || merged.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-muted text-center">
        {t(locale, "evolution.ic.empty")}
      </p>
    );
  }

  return (
    <div className="w-full px-1 pb-2 pt-2" style={{ height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
            interval="preserveStartEnd"
            minTickGap={40}
            stroke="var(--tm-rule)"
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
            tickFormatter={(v: number) => v.toFixed(2)}
            domain={["auto", "auto"]}
            stroke="var(--tm-rule)"
          />
          <Tooltip
            content={(p) => (
              <IcTooltip
                active={p.active}
                payload={p.payload as unknown as Array<{ payload?: MergedRow }>}
                annByTs={annByTs}
                locale={locale}
              />
            )}
          />
          <Legend
            wrapperStyle={{
              fontSize: 11,
              fontFamily: "var(--font-jetbrains-mono)",
            }}
          />
          <ReferenceLine
            y={0}
            stroke="var(--tm-rule-2)"
            strokeDasharray="4 4"
          />
          {series.map((s, i) => (
            <Line
              key={s.signal_name}
              type="monotone"
              dataKey={s.signal_name}
              name={`${getSignalDisplayLabel(s.signal_name, locale)} (${nativeHorizon(s.signal_name)}d)`}
              stroke={SIGNAL_COLORS[i % SIGNAL_COLORS.length]}
              strokeWidth={2}
              dot={(props) => annotationDot(s.signal_name, annByKey, props)}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
