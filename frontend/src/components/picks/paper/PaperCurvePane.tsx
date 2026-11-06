"use client";

import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";
import { useMemo } from "react";
import type { EquityCurveResponse } from "@/lib/api/paper";
import { normalizePaperCurve } from "@/lib/paper-curve";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { Disclaimer } from "./PaperUi";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TM_CHART_CSS, TM_CHART_TYPOGRAPHY } from "@/components/charts/chartTokens";

export default function PaperCurvePane({
  curve,
  compact = false,
  showDisclaimer = true,
}: {
  readonly curve: EquityCurveResponse | null;
  readonly compact?: boolean;
  readonly showDisclaimer?: boolean;
}) {
  const { locale } = useLocale();
  const normalizedSeries = useMemo(
    () => normalizePaperCurve(curve?.series ?? []),
    [curve],
  );
  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {curve && curve.series.length > 0 && normalizedSeries.length === 0 ? (
        <TmStatePane state="partial" title={t(locale,"sim.bot.missing_marks")} className="!min-h-[148px] border-0 !bg-transparent !px-0 !py-3" />
      ) : !curve || normalizedSeries.length === 0 ? (
        <TmStatePane state="empty" title={locale === "zh" ? "等待首个净值记录" : "Awaiting the first equity mark"} description={locale === "zh" ? "目前还没有日终估值。记录产生后，会在同一起点比较个人模拟仓与 SPY；没有数据不代表零收益。" : "No daily valuations yet. Once recorded, your paper account and SPY are compared from a common start. Missing data is not a zero return."} className="!min-h-[148px] border-0 !bg-transparent !px-0 !py-3" />
      ) : (
        <div style={{ width: "100%", height: compact ? 210 : 300 }}>
          <ResponsiveContainer>
            <ComposedChart data={normalizedSeries as unknown as Record<string, unknown>[]} accessibilityLayer>
              <CartesianGrid strokeDasharray="3 3" stroke={TM_CHART_CSS.grid} />
              <XAxis dataKey="date" minTickGap={48} tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: TM_CHART_CSS.muted, fontFamily: "var(--font-tm-mono)" }} />
              <YAxis domain={["auto","auto"]} tickFormatter={value=>Number(value).toFixed(1)} tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: TM_CHART_CSS.muted, fontFamily: "var(--font-tm-mono)" }} />
              <Tooltip contentStyle={{background:TM_CHART_CSS.surface,border:`1px solid ${TM_CHART_CSS.grid}`,color:TM_CHART_CSS.foreground,fontSize:TM_CHART_TYPOGRAPHY.tooltip}} formatter={value=>typeof value === "number" ? value.toFixed(2) : "—"} />
              <Legend wrapperStyle={{ fontSize: TM_CHART_TYPOGRAPHY.legend }} />
              <ReferenceLine y={100} stroke={TM_CHART_CSS.gridStrong} />
              <Line
                connectNulls={false}
                type="linear"
                dataKey="portfolio_index"
                stroke="var(--tm-accent)"
                dot={normalizedSeries.length===1}
                isAnimationActive={false}
                name={t(locale, "sim.account.nav")}
              />
              <Line
                connectNulls={false}
                type="linear"
                dataKey="benchmark_index"
                stroke="var(--tm-muted)"
                strokeDasharray="4 2"
                dot={normalizedSeries.length===1}
                isAnimationActive={false}
                name="SPY"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      {normalizedSeries.some(point=>point.portfolio_index === null || point.benchmark_index === null) ? <p className="text-xs leading-5 text-tm-muted">{t(locale,"sim.bot.curve_gaps")}</p> : null}
      {showDisclaimer ? <Disclaimer /> : null}
    </div>
  );
}
