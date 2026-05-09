"use client";

/**
 * TmICTimeseriesChart — workstation port of ICTimeseriesChart.
 *
 * Recharts ComposedChart of daily IC (bars) overlaid with rolling-mean
 * IC (line). Above the chart: a 4-cell TmKpiGrid surfacing IC mean /
 * std / IR / hit-rate with green/red tone on the directional ones.
 *
 * Chart palette uses the workstation `--tm-*` token namespace so bars
 * and line read terminal-green instead of legacy Linear-blue. Tooltip
 * background uses tm-bg-2 with a tm-rule border to stay in-aesthetic.
 */

import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ICTimeseriesResponse } from "@/lib/types";

interface TmICTimeseriesChartProps {
  readonly data: ICTimeseriesResponse | null;
  readonly loading: boolean;
}

export function TmICTimeseriesChart({
  data,
  loading,
}: TmICTimeseriesChartProps) {
  const { locale } = useLocale();
  const meta = data
    ? t(locale, "signal.ic.title").replace("{n}", String(data.lookback))
    : undefined;

  if (loading && !data) {
    return (
      <TmPane title="IC.TIMESERIES" meta="LOADING">
        <p className="px-3 py-12 text-center font-tm-mono text-[11px] text-tm-muted">
          …
        </p>
      </TmPane>
    );
  }
  if (!data) {
    return (
      <TmPane title="IC.TIMESERIES">
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "signal.today.empty")}
        </p>
      </TmPane>
    );
  }

  return (
    <TmPane title="IC.TIMESERIES" meta={meta}>
      <TmKpiGrid>
        <TmKpi
          label="IC MEAN"
          value={data.summary.ic_mean.toFixed(4)}
          tone={data.summary.ic_mean > 0 ? "pos" : "neg"}
        />
        <TmKpi label="IC STD" value={data.summary.ic_std.toFixed(4)} />
        <TmKpi
          label="IR"
          value={data.summary.ic_ir.toFixed(2)}
          tone={data.summary.ic_ir > 0 ? "pos" : "neg"}
        />
        <TmKpi
          label="HIT RATE"
          value={`${(data.summary.hit_rate * 100).toFixed(1)}%`}
          tone={data.summary.hit_rate > 0.5 ? "pos" : "neg"}
        />
      </TmKpiGrid>

      <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "signal.ic.subtitle")}
      </p>

      <div className="h-[300px] w-full px-1 pb-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={data.points}
            margin={{ top: 10, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              interval="preserveStartEnd"
              minTickGap={30}
              stroke="var(--tm-rule)"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
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
              formatter={(v) =>
                typeof v === "number" ? v.toFixed(4) : String(v ?? "")
              }
            />
            <Legend
              wrapperStyle={{
                fontSize: 11,
                fontFamily: "var(--font-jetbrains-mono)",
              }}
            />
            <ReferenceLine y={0} stroke="var(--tm-rule-2)" strokeWidth={1.2} />
            <Bar
              dataKey="ic"
              name={t(locale, "signal.ic.legendDaily")}
              fill="var(--tm-accent)"
              opacity={0.45}
            />
            <Line
              type="monotone"
              dataKey="rolling_mean"
              name={t(locale, "signal.ic.legendRolling")}
              stroke="var(--tm-accent)"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </TmPane>
  );
}
