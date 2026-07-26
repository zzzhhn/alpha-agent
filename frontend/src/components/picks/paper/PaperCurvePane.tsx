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
import type { EquityCurveResponse } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { Disclaimer } from "./PaperUi";

export default function PaperCurvePane({ curve }: { readonly curve: EquityCurveResponse | null }) {
  const { locale } = useLocale();
  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {!curve || curve.series.length === 0 ? (
        <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.noData")}</p>
      ) : (
        <div style={{ width: "100%", height: 300 }}>
          <ResponsiveContainer>
            <ComposedChart data={curve.series as unknown as Record<string, unknown>[]}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-tm-rule)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fontFamily: "var(--font-tm-mono)" }} />
              <YAxis tick={{ fontSize: 10, fontFamily: "var(--font-tm-mono)" }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="portfolio_value"
                stroke="var(--color-tm-accent)"
                dot={false}
                name={t(locale, "sim.account.nav")}
              />
              <Line
                type="monotone"
                dataKey="benchmark_index"
                stroke="var(--color-tm-muted)"
                strokeDasharray="4 2"
                dot={false}
                name="SPY"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
      <Disclaimer />
    </div>
  );
}
