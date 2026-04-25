"use client";

import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ICTimeseriesResponse } from "@/lib/types";

interface ICTimeseriesChartProps {
  readonly data: ICTimeseriesResponse | null;
  readonly loading: boolean;
}

export function ICTimeseriesChart({ data, loading }: ICTimeseriesChartProps) {
  const { locale } = useLocale();
  const titleStr = data
    ? t(locale, "signal.ic.title").replace("{n}", String(data.lookback))
    : t(locale, "signal.ic.title").replace("{n}", "—");

  return (
    <Card padding="md">
      <header className="mb-2">
        <h2 className="text-sm font-semibold text-text">{titleStr}</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          {t(locale, "signal.ic.subtitle")}
        </p>
      </header>

      {loading && <p className="py-12 text-center text-[11px] text-muted">…</p>}

      {!loading && data && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 text-[11px] md:grid-cols-4">
            <KPI label={t(locale, "signal.ic.mean")} value={data.summary.ic_mean.toFixed(4)} accent={data.summary.ic_mean > 0 ? "green" : "red"} />
            <KPI label={t(locale, "signal.ic.std")} value={data.summary.ic_std.toFixed(4)} />
            <KPI label={t(locale, "signal.ic.ir")} value={data.summary.ic_ir.toFixed(2)} accent={data.summary.ic_ir > 0 ? "green" : "red"} />
            <KPI label={t(locale, "signal.ic.hitRate")} value={`${(data.summary.hit_rate * 100).toFixed(1)}%`} accent={data.summary.hit_rate > 0.5 ? "green" : "red"} />
          </div>

          <div className="h-[280px] w-full">
            <ResponsiveContainer>
              <ComposedChart data={data.points} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--muted)" }} interval="preserveStartEnd" minTickGap={30} />
                <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} />
                <Tooltip
                  contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--border)", fontSize: 11 }}
                  formatter={(v) => (typeof v === "number" ? v.toFixed(4) : String(v ?? ""))}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.2} />
                <Bar dataKey="ic" name={t(locale, "signal.ic.legendDaily")} fill="var(--accent)" opacity={0.45} />
                <Line type="monotone" dataKey="rolling_mean" name={t(locale, "signal.ic.legendRolling")}
                  stroke="var(--accent)" strokeWidth={2} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  );
}

function KPI({ label, value, accent }: { label: string; value: string; accent?: "green" | "red" }) {
  const color = accent === "green" ? "text-green" : accent === "red" ? "text-red" : "text-text";
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
