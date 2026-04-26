"use client";

import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { CoverageResponse, FieldCoverage } from "@/lib/types";

interface CoverageOverviewProps {
  readonly coverage: CoverageResponse;
}

const CATEGORY_LABEL_KEY = {
  ohlcv: "data.coverage.catOhlcv",
  metadata: "data.coverage.catMetadata",
  fundamental: "data.coverage.catFundamental",
} as const;

// HSL ramp green→amber→red. 100% green, 90% amber, <80% red.
function colorFor(rate: number): string {
  if (rate >= 0.99) return "#22c55e"; // green
  if (rate >= 0.95) return "#84cc16"; // lime
  if (rate >= 0.85) return "#eab308"; // amber
  if (rate >= 0.70) return "#f97316"; // orange
  return "#ef4444"; // red
}

export function CoverageOverview({ coverage }: CoverageOverviewProps) {
  const { locale } = useLocale();

  // Group fields by category for the bar chart
  const byCategory = new Map<string, FieldCoverage[]>();
  for (const f of coverage.field_coverage) {
    if (!byCategory.has(f.category)) byCategory.set(f.category, []);
    byCategory.get(f.category)!.push(f);
  }

  const worstTickers = coverage.ticker_coverage.slice(0, 6); // already sorted asc

  return (
    <Card padding="md">
      <header className="mb-4">
        <h2 className="text-base font-semibold text-text">
          {t(locale, "data.coverage.title")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">
          {t(locale, "data.coverage.subtitle")}
        </p>
      </header>

      {/* Top KPI strip */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label={t(locale, "data.coverage.kTickers")} value={coverage.n_tickers.toString()} />
        <Kpi label={t(locale, "data.coverage.kDays")} value={coverage.n_days.toString()} />
        <Kpi
          label={t(locale, "data.coverage.kOhlcvPct")}
          value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`}
          accent={coverage.ohlcv_coverage_pct >= 99 ? "green" : "yellow"}
        />
        <Kpi
          label={t(locale, "data.coverage.kRange")}
          value={`${coverage.start_date} → ${coverage.end_date}`}
          mono
        />
      </div>

      {/* Per-field fill rate bars, grouped by category */}
      <div className="space-y-4">
        {(["ohlcv", "metadata", "fundamental"] as const).map((cat) => {
          const fields = byCategory.get(cat);
          if (!fields || fields.length === 0) return null;
          return (
            <section key={cat}>
              <h3 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
                {t(locale, CATEGORY_LABEL_KEY[cat])} ({fields.length})
              </h3>
              <div className="space-y-1">
                {fields.map((f) => (
                  <FieldBar key={f.name} field={f} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {/* Worst-coverage tickers (only show if any have <100%) */}
      {worstTickers.length > 0 && worstTickers[0].fill_rate < 1.0 && (
        <section className="mt-4 border-t border-border pt-4">
          <h3 className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
            {t(locale, "data.coverage.worstTickers")}
          </h3>
          <div className="space-y-1">
            {worstTickers.filter((t) => t.fill_rate < 1.0).map((tk) => (
              <div key={tk.ticker} className="flex items-center gap-3 text-[13px]">
                <span className="w-20 font-mono text-text">{tk.ticker}</span>
                <div className="relative h-4 flex-1 overflow-hidden rounded bg-[var(--toggle-bg)]">
                  <div
                    className="h-full"
                    style={{
                      width: `${tk.fill_rate * 100}%`,
                      background: colorFor(tk.fill_rate),
                    }}
                  />
                </div>
                <span className="w-16 text-right font-mono text-text">
                  {(tk.fill_rate * 100).toFixed(1)}%
                </span>
                <span className="w-20 text-right font-mono text-muted">
                  {tk.n_missing} missing
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="mt-4 text-[12px] leading-relaxed text-muted">
        {t(locale, "data.coverage.legend")}
      </p>
    </Card>
  );
}

function FieldBar({ field }: { field: FieldCoverage }) {
  return (
    <div className="flex items-center gap-3 text-[13px]">
      <code className="w-44 truncate font-mono text-text" title={field.name}>
        {field.name}
      </code>
      <div className="relative h-5 flex-1 overflow-hidden rounded bg-[var(--toggle-bg)]">
        <div
          className="h-full"
          style={{
            width: `${field.fill_rate * 100}%`,
            background: colorFor(field.fill_rate),
            transition: "width 200ms",
          }}
        />
      </div>
      <span className="w-16 text-right font-mono text-text">
        {(field.fill_rate * 100).toFixed(1)}%
      </span>
      <span className="w-24 text-right font-mono text-[12px] text-muted">
        {field.n_present.toLocaleString()} / {field.n_total.toLocaleString()}
      </span>
    </div>
  );
}

function Kpi({
  label, value, accent, mono,
}: {
  label: string;
  value: string;
  accent?: "green" | "yellow";
  mono?: boolean;
}) {
  const color = accent === "green" ? "text-green" : accent === "yellow" ? "text-yellow" : "text-text";
  return (
    <div>
      <div className="text-[12px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 ${mono ? "font-mono" : ""} text-base font-semibold ${color}`}>
        {value}
      </div>
    </div>
  );
}
