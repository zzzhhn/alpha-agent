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
} from "recharts";
import { useMemo } from "react";
import type { EquityCurveResponse } from "@/lib/api/paper";
import { normalizePaperCurve } from "@/lib/paper-curve";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { Disclaimer } from "./PaperUi";
import { TmStatePane } from "@/components/tm/TmStatePane";

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
      {!curve || normalizedSeries.length === 0 ? (
        <TmStatePane state="empty" title={locale === "zh" ? "等待首个净值记录" : "Awaiting the first equity mark"} description={locale === "zh" ? "目前还没有日终估值。记录产生后，会在同一起点比较个人模拟仓与 SPY；没有数据不代表零收益。" : "No daily valuations yet. Once recorded, your paper account and SPY are compared from a common start. Missing data is not a zero return."} className="!min-h-[148px] border-0 !bg-transparent !px-0 !py-3" />
      ) : (
        <div style={{ width: "100%", height: compact ? 210 : 300 }}>
          <ResponsiveContainer>
            <ComposedChart data={normalizedSeries as unknown as Record<string, unknown>[]}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-tm-rule)" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fontFamily: "var(--font-tm-mono)" }} />
              <YAxis tick={{ fontSize: 12, fontFamily: "var(--font-tm-mono)" }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="portfolio_index"
                stroke="var(--tm-accent)"
                dot={false}
                name={t(locale, "sim.account.nav")}
              />
              <Line
                type="monotone"
                dataKey="benchmark_index"
                stroke="var(--tm-muted)"
                strokeDasharray="4 2"
                dot={false}
                name="SPY"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      {showDisclaimer ? <Disclaimer /> : null}
    </div>
  );
}
