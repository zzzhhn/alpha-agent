"use client";

/**
 * TmMonthlyReturnsHeatmap — workstation port of MonthlyReturnsHeatmap.
 *
 * Year × month grid; cell color ramps green-positive → red-negative,
 * intensity scaled to ±10% per month so a single +30% outlier doesn't
 * flatten everything else. Year totals shown in the right-most column
 * (compounded, not summed).
 *
 * Uses the canonical diverging heatmap ramp, with readable foreground text
 * on both themes. The +/- sign and legend supplement the semantic colors.
 */

import { TmPane } from "@/components/tm/TmPane";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { MonthlyReturn } from "@/lib/types";
import { TmTooltip } from "@/components/tm/TmTooltip";
import { TM_CHART_CSS, tmHeatmapColor } from "@/components/charts/chartTokens";

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

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
      meta={locale === "zh" ? `${years.length} 年 · 复利收益` : `${years.length} years · compounded`}
    >
      <p className="border-b border-tm-rule px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-muted">
        {t(locale, "backtest.monthly.subtitle")}
      </p>
      <div className="overflow-x-auto px-3 py-3">
        <table
          className="w-full border-separate font-tm-mono"
          style={{ borderSpacing: 2 }}
        >
          <caption className="sr-only">
            {locale === "zh" ? "按年份和月份展示的回测收益热力图" : "Backtest returns heatmap by year and month"}
          </caption>
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-tm-bg px-2 py-1 text-left text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted">
                {t(locale, "backtest.monthly.year")}
              </th>
              {MONTH_LABELS.map((m, index) => (
                <th
                  key={m}
                  className="px-1 py-1 text-center text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted"
                >
                  {locale === "zh" ? `${index + 1}月` : m}
                </th>
              ))}
              <th className="px-2 py-1 text-right text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted">
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
                  <td className="sticky left-0 z-10 bg-tm-bg px-2 py-1 text-xs text-tm-fg">
                    {y}
                  </td>
                  {MONTH_LABELS.map((_l, idx) => {
                    const m = months.get(idx + 1);
                    if (!m) {
                      return (
                        <td
                          key={idx}
                          className="border border-tm-rule bg-tm-bg-2 px-1 py-1 text-center text-xs text-tm-muted"
                        >
                          <TmTooltip
                            content={locale === "zh" ? "该月无回测数据" : "No backtest data for this month"}
                            ariaLabel={locale === "zh" ? "无数据" : "No data"}
                            className="w-full justify-center"
                          >
                            —
                          </TmTooltip>
                        </td>
                      );
                    }
                    return (
                      <td
                        key={idx}
                        className="px-1 py-1 text-center text-xs font-medium"
                        style={{
                          background: tmHeatmapColor(m.return),
                          color: TM_CHART_CSS.foreground,
                        }}
                      >
                        <TmTooltip
                          content={`${y}-${String(m.month).padStart(2, "0")}: ${(m.return * 100).toFixed(2)}% (${m.n_days} d)`}
                          ariaLabel={`${y}-${String(m.month).padStart(2, "0")}`}
                          className="w-full justify-center"
                        >
                          {(m.return * 100).toFixed(1)}
                        </TmTooltip>
                      </td>
                    );
                  })}
                  <td
                    className={`px-2 py-1 text-right text-xs font-semibold tabular-nums ${total >= 0 ? "text-tm-pos" : "text-tm-neg"}`}
                  >
                    {(total * 100).toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-tm-rule px-3 py-1.5 font-tm-mono text-xs text-tm-muted">
        {t(locale, "backtest.monthly.legend")}
      </p>
    </TmPane>
  );
}
