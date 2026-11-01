"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TM_CHART_CSS, TM_CHART_SERIES_CSS, TM_CHART_TYPOGRAPHY } from "./chartTokens";

export type RecommendationNavPoint = {
  date: string; net: number | null; spy: number | null; rsp: number | null;
  cash: number; stale: boolean;
};

export default function RecommendationNavChart({ series, zh }: {
  series: RecommendationNavPoint[]; zh: boolean;
}) {
  if (series.length < 2) return <p className="text-xs text-tm-muted">{zh
    ? "等待至少两个交易日估值。系统会在收盘行情更新后自动记账，无需手动下单。"
    : "Waiting for two session marks. The system records the research book after daily prices update; no manual order is needed."}</p>;
  const data = series.map(p => ({ ...p, net: p.stale ? null : p.net }));
  return <figure aria-label={zh ? "推荐策略扣费净值，与 SPY、RSP 和现金对照" : "Net recommendation NAV versus SPY, RSP and cash"}>
    <div className="h-72 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 800, height: 288 }}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} accessibilityLayer>
          <CartesianGrid stroke={TM_CHART_CSS.grid} strokeDasharray="2 4" />
          <XAxis dataKey="date" tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: TM_CHART_CSS.muted }} minTickGap={60} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: TM_CHART_TYPOGRAPHY.tick, fill: TM_CHART_CSS.muted }} tickFormatter={v => Number(v).toFixed(1)} width={52} />
          <Tooltip contentStyle={{ background: TM_CHART_CSS.surface, border: `1px solid ${TM_CHART_CSS.grid}`, fontSize: TM_CHART_TYPOGRAPHY.tooltip, color: TM_CHART_CSS.foreground }} formatter={v => typeof v === "number" ? v.toFixed(2) : "—"} />
          <Legend wrapperStyle={{ fontSize: TM_CHART_TYPOGRAPHY.legend }} />
          <ReferenceLine y={100} stroke={TM_CHART_CSS.gridStrong} />
          {[["net", zh ? "策略净值" : "Net strategy NAV"], ["spy", "SPY"], ["rsp", "RSP"], ["cash", zh ? "现金" : "Cash"]].map(([key, name], i) =>
            <Line key={key} type="linear" dataKey={key} name={name} stroke={i === 3 ? TM_CHART_CSS.muted : TM_CHART_SERIES_CSS[i]} strokeWidth={i === 0 ? 2 : 1.5} strokeDasharray={i === 0 ? undefined : "4 3"} dot={false} connectNulls={false} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
    <figcaption className="mt-2 text-xs text-tm-muted">{zh
      ? "起始资金指数 100，保留首次建仓成本。断线代表缺失或过期估值，不按零收益补齐。"
      : "Starting capital = 100, including initial entry costs. Gaps indicate missing or stale marks, never assumed zero returns."}</figcaption>
  </figure>;
}
