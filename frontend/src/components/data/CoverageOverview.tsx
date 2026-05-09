"use client";

/**
 * Coverage overview — flat workstation pane.
 *
 * Renders inside TmScreen as a single TmPane with a tm-kpis strip up
 * top + per-category fill-rate bars + worst-coverage tickers list.
 * No outer card — borders come from the screen's child-hairline rule.
 */

import { TmPane } from "@/components/tm/TmPane";
import { TmKpi, TmKpiGrid } from "@/components/tm/TmKpi";
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

// Coverage health colour ramp — uses theme tokens. The hex fallbacks
// preserve the legacy lime/orange middle steps that don't have direct
// tokens.
function colorFor(rate: number): string {
  if (rate >= 0.99) return "var(--tm-pos)";
  if (rate >= 0.95) return "#84cc16"; // lime
  if (rate >= 0.85) return "var(--tm-warn)";
  if (rate >= 0.7) return "#f97316"; // orange
  return "var(--tm-neg)";
}

export function CoverageOverview({ coverage }: CoverageOverviewProps) {
  const { locale } = useLocale();

  const byCategory = new Map<string, FieldCoverage[]>();
  for (const f of coverage.field_coverage) {
    if (!byCategory.has(f.category)) byCategory.set(f.category, []);
    byCategory.get(f.category)!.push(f);
  }

  const worstTickers = coverage.ticker_coverage
    .slice(0, 6)
    .filter((tk) => tk.fill_rate < 1.0);

  return (
    <TmPane title="DATA.COVERAGE" meta={t(locale, "data.coverage.subtitle")}>
      <TmKpiGrid>
        <TmKpi
          label={t(locale, "data.coverage.kTickers")}
          value={coverage.n_tickers.toString()}
        />
        <TmKpi
          label={t(locale, "data.coverage.kDays")}
          value={coverage.n_days.toLocaleString()}
        />
        <TmKpi
          label={t(locale, "data.coverage.kOhlcvPct")}
          value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`}
          tone={coverage.ohlcv_coverage_pct >= 99 ? "pos" : "warn"}
        />
        <TmKpi
          label={t(locale, "data.coverage.kRange")}
          value={coverage.start_date}
          sub={`→ ${coverage.end_date}`}
        />
      </TmKpiGrid>

      {(["ohlcv", "metadata", "fundamental"] as const).map((cat) => {
        const fields = byCategory.get(cat);
        if (!fields || fields.length === 0) return null;
        return (
          <section key={cat} className="border-t border-tm-rule">
            <div className="px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted">
              {t(locale, CATEGORY_LABEL_KEY[cat])} ({fields.length})
            </div>
            <div className="flex flex-col gap-1 px-3 pb-2">
              {fields.map((f) => (
                <FieldBar key={f.name} field={f} />
              ))}
            </div>
          </section>
        );
      })}

      {worstTickers.length > 0 && (
        <section className="border-t border-tm-rule">
          <div className="px-3 py-1 font-tm-mono text-[10px] uppercase tracking-[0.10em] text-tm-muted">
            {t(locale, "data.coverage.worstTickers")}
          </div>
          <div className="flex flex-col gap-1 px-3 pb-2 font-tm-mono">
            {worstTickers.map((tk) => (
              <div
                key={tk.ticker}
                className="flex items-center gap-3 text-[11px]"
              >
                <span className="w-20 font-semibold text-tm-fg">
                  {tk.ticker}
                </span>
                <div className="relative h-2.5 flex-1 overflow-hidden bg-tm-bg-3">
                  <div
                    className="h-full"
                    style={{
                      width: `${tk.fill_rate * 100}%`,
                      background: colorFor(tk.fill_rate),
                    }}
                  />
                </div>
                <span className="w-14 text-right tabular-nums text-tm-fg">
                  {(tk.fill_rate * 100).toFixed(1)}%
                </span>
                <span className="w-20 text-right text-[10px] text-tm-muted">
                  {tk.n_missing} missing
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10px] leading-relaxed text-tm-muted">
        {t(locale, "data.coverage.legend")}
      </p>
    </TmPane>
  );
}

function FieldBar({ field }: { field: FieldCoverage }) {
  return (
    <div className="flex items-center gap-3 font-tm-mono text-[11px]">
      <code className="w-44 truncate text-tm-fg" title={field.name}>
        {field.name}
      </code>
      <div className="relative h-3 flex-1 overflow-hidden bg-tm-bg-3">
        <div
          className="h-full transition-[width] duration-200"
          style={{
            width: `${field.fill_rate * 100}%`,
            background: colorFor(field.fill_rate),
          }}
        />
      </div>
      <span className="w-14 text-right tabular-nums text-tm-fg">
        {(field.fill_rate * 100).toFixed(1)}%
      </span>
      <span className="w-24 text-right text-[10px] text-tm-muted">
        {field.n_present.toLocaleString()} / {field.n_total.toLocaleString()}
      </span>
    </div>
  );
}
