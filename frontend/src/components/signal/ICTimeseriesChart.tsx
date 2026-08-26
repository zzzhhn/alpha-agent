"use client";

import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { TmPane } from "@/components/tm/TmPane";
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
    <TmPane standalone title={titleStr} bodyClassName="p-4">
      <header className="mb-2">
        <p className="text-xs leading-5 text-tm-muted">
          {t(locale, "signal.ic.subtitle")}
        </p>
      </header>

      {loading && <p className="py-12 text-center text-xs text-tm-muted">…</p>}

      {!loading && data && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
            <KPI label={t(locale, "signal.ic.mean")} value={data.summary.ic_mean.toFixed(4)} accent={data.summary.ic_mean > 0 ? "green" : "red"} />
            <KPI label={t(locale, "signal.ic.std")} value={data.summary.ic_std.toFixed(4)} />
            <KPI label={t(locale, "signal.ic.ir")} value={data.summary.ic_ir.toFixed(2)} accent={data.summary.ic_ir > 0 ? "green" : "red"} />
            <KPI label={t(locale, "signal.ic.hitRate")} value={`${(data.summary.hit_rate * 100).toFixed(1)}%`} accent={data.summary.hit_rate > 0.5 ? "green" : "red"} />
          </div>

          <div className="h-[280px] w-full">
            <ResponsiveContainer>
              <ComposedChart data={data.points} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="var(--tm-rule)" />
                <XAxis dataKey="date" tick={{ fontSize: 12, fill: "var(--tm-muted)" }} interval="preserveStartEnd" minTickGap={30} />
                <YAxis tick={{ fontSize: 12, fill: "var(--tm-muted)" }} />
                <Tooltip
                  contentStyle={{ background: "var(--tm-bg-2)", border: "1px solid var(--tm-rule)", borderRadius: 0, fontSize: 12 }}
                  formatter={(v) => (typeof v === "number" ? v.toFixed(4) : String(v ?? ""))}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={0} stroke="var(--tm-rule)" strokeWidth={1.2} />
                <Bar dataKey="ic" name={t(locale, "signal.ic.legendDaily")} fill="var(--tm-accent)" opacity={0.45} />
                <Line type="monotone" dataKey="rolling_mean" name={t(locale, "signal.ic.legendRolling")}
                  stroke="var(--tm-accent)" strokeWidth={2} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </TmPane>
  );
}

function KPI({ label, value, accent }: { label: string; value: string; accent?: "green" | "red" }) {
  const color = accent === "green" ? "text-tm-pos" : accent === "red" ? "text-tm-neg" : "text-tm-fg";
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-tm-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-base ${color}`}>{value}</div>
    </div>
  );
}
