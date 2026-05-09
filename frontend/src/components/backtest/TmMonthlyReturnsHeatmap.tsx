"use client";

/**
 * TmMonthlyReturnsHeatmap — workstation port of MonthlyReturnsHeatmap.
 *
 * Year × month grid; cell color ramps green-positive → red-negative,
 * intensity scaled to ±10% per month so a single +30% outlier doesn't
 * flatten everything else. Year totals shown in the right-most column
 * (compounded, not summed).
 *
 * Reuses the same hsl ramp logic from the legacy version — colors are
 * picked to read on both light and dark workstation backgrounds (the
 * tm tokens themselves don't extend into a 2D ramp, so hsl literals
 * are kept here).
 */

import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { MonthlyReturn } from "@/lib/types";

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function colorFor(ret: number): string {
  if (!isFinite(ret)) return "transparent";
  const clipped = Math.max(-0.1, Math.min(0.1, ret));
  const intensity = Math.abs(clipped) / 0.1;
  const lightness = 90 - 30 * intensity;
  if (clipped >= 0) return `hsl(142, 70%, ${lightness}%)`;
  return `hsl(0, 70%, ${lightness}%)`;
}

function textColorFor(ret: number): string {
  if (Math.abs(ret) > 0.05) return "rgb(20, 30, 40)";
  return "var(--tm-fg)";
}

export function TmMonthlyReturnsHeatmap({
  data,
}: {
  readonly data: readonly MonthlyReturn[];
}) {
  const { locale } = useLocale();
  if (!data || data.length === 0) return null;

  const byYear = new Map<number, Map<number, MonthlyReturn>>();
  for (const m of data) {
    if (!byYear.has(m.year)) byYear.set(m.year, new Map());
    byYear.get(m.year)!.set(m.month, m);
  }
  const years = Array.from(byYear.keys()).sort();

  function yearTotal(year: number): number {
    const months = byYear.get(year);
    if (!months) return 0;
    let prod = 1;
    Array.from(months.values()).forEach((m) => {
      prod *= 1 + m.return;
    });
    return prod - 1;
  }

  return (
    <TmPane
      title="MONTHLY.RETURNS"
      meta={`${years.length} YEAR${years.length === 1 ? "" : "S"} · compounded`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "backtest.monthly.subtitle")}
      </p>
      <div className="overflow-x-auto px-3 py-3">
        <table
          className="w-full border-separate font-tm-mono"
          style={{ borderSpacing: 2 }}
        >
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-tm-bg px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
                {t(locale, "backtest.monthly.year")}
              </th>
              {MONTH_LABELS.map((m) => (
                <th
                  key={m}
                  className="px-1 py-1 text-center text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted"
                >
                  {m}
                </th>
              ))}
              <th className="px-2 py-1 text-right text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted">
                {t(locale, "backtest.monthly.total")}
              </th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => {
              const months = byYear.get(y)!;
              const total = yearTotal(y);
              return (
                <tr key={y}>
                  <td className="sticky left-0 z-10 bg-tm-bg px-2 py-1 text-[11px] text-tm-fg">
                    {y}
                  </td>
                  {MONTH_LABELS.map((_l, idx) => {
                    const m = months.get(idx + 1);
                    if (!m) {
                      return (
                        <td
                          key={idx}
                          className="border border-tm-rule bg-tm-bg-2 px-1 py-1 text-center text-[10.5px] text-tm-muted"
                          title="no data"
                        >
                          —
                        </td>
                      );
                    }
                    return (
                      <td
                        key={idx}
                        className="px-1 py-1 text-center text-[10.5px] font-medium"
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
                    className={`px-2 py-1 text-right text-[11px] font-semibold tabular-nums ${total >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
                  >
                    {(total * 100).toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-tm-rule px-3 py-1.5 font-tm-mono text-[10px] text-tm-muted">
        {t(locale, "backtest.monthly.legend")}
      </p>
    </TmPane>
  );
}
