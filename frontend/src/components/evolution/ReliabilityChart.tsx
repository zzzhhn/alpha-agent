"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { EvolutionCalibration } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";

interface ReliabilityChartProps {
  readonly calibration: EvolutionCalibration;
  readonly locale: Locale;
}

interface BucketPoint {
  readonly mid: number;
  readonly hit_rate: number;
  readonly brier: number | null;
  readonly n: number;
}

function buildBucketPoints(calibration: EvolutionCalibration): BucketPoint[] {
  return calibration.buckets
    .filter((b) => b.n > 0 && b.hit_rate !== null)
    .map((b) => ({
      mid: (b.lo + b.hi) / 2,
      hit_rate: b.hit_rate as number,
      brier: b.brier,
      n: b.n,
    }));
}

// Perfect calibration reference: y = x at [0, 0.1, 0.2, ..., 1.0].
const PERFECT_LINE = Array.from({ length: 11 }, (_, i) => ({
  mid: i / 10,
  perfect: i / 10,
}));

function meanBrier(calibration: EvolutionCalibration): number | null {
  const valid = calibration.buckets.filter(
    (b) => b.brier !== null && b.n > 0,
  );
  if (valid.length === 0) return null;
  const totalN = valid.reduce((s, b) => s + b.n, 0);
  const weightedSum = valid.reduce(
    (s, b) => s + (b.brier as number) * b.n,
    0,
  );
  return totalN > 0 ? weightedSum / totalN : null;
}

export function ReliabilityChart({ calibration, locale }: ReliabilityChartProps) {
  if (!calibration.applied) {
    return (
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-warn text-center">
        {t(locale, "evolution.cal.not_applied").replace(
          "{n}",
          String(calibration.n_pairs),
        )}
      </p>
    );
  }

  const points = buildBucketPoints(calibration);

  if (points.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-muted text-center">
        {t(locale, "evolution.cal.no_buckets")}
      </p>
    );
  }

  const brier = meanBrier(calibration);

  return (
    <div>
      <div className="w-full px-1 pb-2 pt-2" style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
            <XAxis
              dataKey="mid"
              type="number"
              domain={[0, 1]}
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              tickFormatter={(v: number) => v.toFixed(1)}
              label={{
                value: t(locale, "evolution.cal.axis_predicted"),
                position: "insideBottom",
                offset: -4,
                fill: "var(--tm-muted)",
                fontSize: 10,
              }}
              stroke="var(--tm-rule)"
            />
            <YAxis
              dataKey="hit_rate"
              type="number"
              domain={[0, 1]}
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              tickFormatter={(v: number) => v.toFixed(1)}
              label={{
                value: t(locale, "evolution.cal.axis_actual"),
                angle: -90,
                position: "insideLeft",
                fill: "var(--tm-muted)",
                fontSize: 10,
                dy: 40,
              }}
              stroke="var(--tm-rule)"
            />
            <Tooltip
              contentStyle={{
                background: "var(--tm-bg-2)",
                border: "1px solid var(--tm-rule)",
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
                color: "var(--tm-fg)",
              }}
              formatter={(v, name) => {
                const num = typeof v === "number" ? v : Number(v);
                if (name === "hit_rate")
                  return [num.toFixed(3), t(locale, "evolution.cal.tip_hitrate")];
                if (name === "perfect")
                  return [num.toFixed(2), t(locale, "evolution.cal.tip_perfect")];
                return [String(v ?? ""), String(name)];
              }}
              labelFormatter={(l) => `mid=${Number(l).toFixed(2)}`}
            />
            {/* Perfect calibration diagonal */}
            <Line
              data={PERFECT_LINE}
              type="linear"
              dataKey="perfect"
              name="perfect"
              stroke="var(--tm-rule-2)"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
            {/* Actual calibration curve */}
            <Line
              data={points}
              type="monotone"
              dataKey="hit_rate"
              name="hit_rate"
              stroke="var(--tm-accent)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--tm-accent)", strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {brier !== null && (
        <p className="px-1 pb-1 font-tm-mono text-[10px] text-tm-muted text-right">
          {t(locale, "evolution.cal.brier").replace("{v}", brier.toFixed(4))}
          {calibration.as_of ? ` · ${calibration.as_of}` : ""}
        </p>
      )}
    </div>
  );
}
