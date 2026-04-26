"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Cell,
} from "recharts";
import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ExposureResponse } from "@/lib/types";

interface ExposureChartProps {
  readonly data: ExposureResponse | null;
  readonly topN: number;
  readonly loading: boolean;
}

export function ExposureChart({ data, topN, loading }: ExposureChartProps) {
  const { locale } = useLocale();
  const subtitle = t(locale, "signal.exposure.subtitle").replace(/\{n\}/g, String(topN));

  return (
    <Card padding="md">
      <header className="mb-2">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "signal.exposure.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">{subtitle}</p>
      </header>

      {loading && <p className="py-12 text-center text-[13px] text-muted">…</p>}

      {!loading && data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SectorBar
            title={t(locale, "signal.exposure.sector")}
            rows={data.sector_exposure.map((s) => ({ name: s.sector, net_pct: s.net_pct }))}
          />
          <SectorBar
            title={t(locale, "signal.exposure.capBucket")}
            rows={data.cap_quintile.map((c) => ({ name: c.bucket, net_pct: c.net_pct }))}
          />
        </div>
      )}
    </Card>
  );
}

function SectorBar({
  title, rows,
}: {
  title: string;
  rows: { name: string; net_pct: number }[];
}) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <div>
      <h4 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
        {title}
      </h4>
      <div className="h-[260px] w-full">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ top: 6, right: 24, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" />
            <XAxis type="number" tick={{ fontSize: 10, fill: "var(--muted)" }}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
            <YAxis type="category" dataKey="name" width={120}
              tick={{ fontSize: 10, fill: "var(--muted)" }} />
            <Tooltip
              contentStyle={{ background: "var(--card-bg)", border: "1px solid var(--border)", fontSize: 11 }}
              formatter={(v) => (typeof v === "number" ? `${v.toFixed(1)}%` : String(v ?? ""))}
            />
            <ReferenceLine x={0} stroke="var(--border)" />
            <Bar dataKey="net_pct" name="Net %">
              {rows.map((r, i) => (
                <Cell key={i} fill={r.net_pct >= 0 ? "var(--green, #22c55e)" : "var(--red, #ef4444)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
