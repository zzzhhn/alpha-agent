"use client";

import { Card } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { MonthlyReturn } from "@/lib/types";

interface MonthlyReturnsHeatmapProps {
  readonly data: readonly MonthlyReturn[];
}

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// HSL ramp: bright green (positive) → red (negative). The intensity scales
// with absolute return clipped at 10% so a single +30% month doesn't
// flatten everything else into a uniform deep green.
function colorFor(ret: number): string {
  if (!isFinite(ret)) return "transparent";
  const clipped = Math.max(-0.10, Math.min(0.10, ret));
  const intensity = Math.abs(clipped) / 0.10;   // 0..1
  const lightness = 90 - 30 * intensity;        // 90% for tiny, 60% for big
  if (clipped >= 0) {
    // green hue 142
    return `hsl(142, 70%, ${lightness}%)`;
  }
  return `hsl(0, 70%, ${lightness}%)`;
}

function textColorFor(ret: number): string {
  if (Math.abs(ret) > 0.05) return "rgb(20, 30, 40)";   // dark text on saturated cells
  return "var(--text)";
}

export function MonthlyReturnsHeatmap({ data }: MonthlyReturnsHeatmapProps) {
  const { locale } = useLocale();
  if (!data || data.length === 0) {
    return null;
  }

  // Build {year: {month: return}} grid
  const byYear = new Map<number, Map<number, MonthlyReturn>>();
  for (const m of data) {
    if (!byYear.has(m.year)) byYear.set(m.year, new Map());
    byYear.get(m.year)!.set(m.month, m);
  }
  const years = Array.from(byYear.keys()).sort();

  // Year-level totals (sum of monthly returns approximation; for compounded
  // visual we'd need to multiply, but additive is fine at sub-year scale)
  function yearTotal(year: number): number {
    const months = byYear.get(year);
    if (!months) return 0;
    let prod = 1;
    Array.from(months.values()).forEach((m) => { prod *= 1 + m.return; });
    return prod - 1;
  }

  return (
    <Card padding="md">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">
          {t(locale, "backtest.monthly.title")}
        </h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          {t(locale, "backtest.monthly.subtitle")}
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-[var(--card-bg)] px-2 py-1 text-left text-[10px] font-medium uppercase tracking-wide text-muted">
                {t(locale, "backtest.monthly.year")}
              </th>
              {MONTH_LABELS.map((m) => (
                <th
                  key={m}
                  className="px-1 py-1 text-center text-[10px] font-medium uppercase tracking-wide text-muted"
                >
                  {m}
                </th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-muted">
                {t(locale, "backtest.monthly.total")}
              </th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => {
              const months = byYear.get(y)!;
              return (
                <tr key={y}>
                  <td className="sticky left-0 z-10 bg-[var(--card-bg)] px-2 py-1 font-mono text-xs text-text">
                    {y}
                  </td>
                  {MONTH_LABELS.map((_label, idx) => {
                    const m = months.get(idx + 1);
                    if (!m) {
                      return (
                        <td
                          key={idx}
                          className="rounded-sm border border-border/30 bg-[var(--toggle-bg)] px-1 py-1 text-center text-[10px] text-muted"
                          title="no data"
                        >
                          —
                        </td>
                      );
                    }
                    return (
                      <td
                        key={idx}
                        className="rounded-sm px-1 py-1 text-center font-mono text-[10px] font-medium"
                        style={{
                          background: colorFor(m.return),
                          color: textColorFor(m.return),
                        }}
                        title={`${y}-${String(m.month).padStart(2, "0")}: ${(m.return * 100).toFixed(2)}% (${m.n_days} d)`}
                      >
                        {(m.return * 100).toFixed(1)}
                      </td>
                    );
                  })}
                  <td
                    className="px-2 py-1 text-right font-mono text-xs font-semibold"
                    style={{ color: yearTotal(y) >= 0 ? "var(--green, #16a34a)" : "var(--red, #ef4444)" }}
                  >
                    {(yearTotal(y) * 100).toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-[10px] text-muted">
        {t(locale, "backtest.monthly.legend")}
      </p>
    </Card>
  );
}
