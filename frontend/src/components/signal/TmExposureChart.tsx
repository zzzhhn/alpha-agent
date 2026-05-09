"use client";

/**
 * TmExposureChart — workstation port of ExposureChart.
 *
 * Two horizontal bar charts side by side: sector net exposure %
 * and cap-quintile net exposure %. Wrapped in a single TmPane with
 * an internal TmCols2 hairline divider so the two charts read as
 * paired sub-views.
 *
 * Bars are color-coded — green for positive net exposure, red for
 * negative — matching the workstation pos/neg tokens.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { TmPane, TmCols2 } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ExposureResponse } from "@/lib/types";

interface TmExposureChartProps {
  readonly data: ExposureResponse | null;
  readonly topN: number;
  readonly loading: boolean;
}

export function TmExposureChart({
  data,
  topN,
  loading,
}: TmExposureChartProps) {
  const { locale } = useLocale();
  const meta = data ? `TOP/BOT ${topN}` : undefined;

  if (loading && !data) {
    return (
      <TmPane title="EXPOSURE" meta="LOADING">
        <p className="px-3 py-12 text-center font-tm-mono text-[11px] text-tm-muted">
          …
        </p>
      </TmPane>
    );
  }
  if (!data) {
    return (
      <TmPane title="EXPOSURE">
        <p className="px-3 py-6 text-center font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "signal.today.empty")}
        </p>
      </TmPane>
    );
  }

  return (
    <TmPane title="EXPOSURE" meta={meta}>
      <p className="px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "signal.exposure.subtitle").replace(/\{n\}/g, String(topN))}
      </p>
      <TmCols2>
        <SubChart
          title={t(locale, "signal.exposure.sector")}
          rows={data.sector_exposure.map((s) => ({
            name: s.sector,
            net_pct: s.net_pct,
          }))}
        />
        <SubChart
          title={t(locale, "signal.exposure.capBucket")}
          rows={data.cap_quintile.map((c) => ({
            name: c.bucket,
            net_pct: c.net_pct,
          }))}
        />
      </TmCols2>
    </TmPane>
  );
}

function SubChart({
  title,
  rows,
}: {
  readonly title: string;
  readonly rows: { name: string; net_pct: number }[];
}) {
  if (rows.length === 0) {
    return (
      <div className="flex items-center justify-center px-3 py-12">
        <span className="font-tm-mono text-[11px] text-tm-muted">no data</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col">
      <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
        {title}
      </div>
      <div className="h-[260px] w-full px-1 pb-2 pt-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 6, right: 24, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
            <XAxis
              type="number"
              tick={{ fontSize: 10, fill: "var(--tm-muted)" }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              stroke="var(--tm-rule)"
            />
            <YAxis
              type="category"
              dataKey="name"
              width={120}
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
                typeof v === "number" ? `${v.toFixed(1)}%` : String(v ?? "")
              }
            />
            <ReferenceLine x={0} stroke="var(--tm-rule-2)" />
            <Bar dataKey="net_pct" name="Net %">
              {rows.map((r, i) => (
                <Cell
                  key={i}
                  fill={
                    r.net_pct >= 0 ? "var(--tm-pos)" : "var(--tm-neg)"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
