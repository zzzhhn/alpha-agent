"use client";

import { TmPane } from "@/components/tm/TmPane";
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

// Coverage health colours — kept on absolute hex values rather than
// theme tokens because the threshold-to-colour mapping is the data's
// signal, not the chrome's accent. The legacy implementation used the
// same ramp; the only delta is the 99% bucket now matches --tm-pos
// (terminal green) instead of Linear's --green.
function colorFor(rate: number): string {
  if (rate >= 0.99) return "var(--tm-pos)";
  if (rate >= 0.95) return "#84cc16"; // lime
  if (rate >= 0.85) return "var(--tm-warn)";
  if (rate >= 0.70) return "#f97316"; // orange
  return "var(--tm-neg)";
}

export function CoverageOverview({ coverage }: CoverageOverviewProps) {
  const { locale } = useLocale();

  const byCategory = new Map<string, FieldCoverage[]>();
  for (const f of coverage.field_coverage) {
    if (!byCategory.has(f.category)) byCategory.set(f.category, []);
    byCategory.get(f.category)!.push(f);
  }

  const worstTickers = coverage.ticker_coverage.slice(0, 6);

  return (
    <TmPane
      title={t(locale, "data.coverage.title")}
      meta={t(locale, "data.coverage.subtitle")}
    >
      {/* KPI strip — 4 metrics in a tight grid against the pane body's
          inner hairlines, mirroring the design's `.tm-mgrid` pattern.
          We render gridded backgrounds via `gap-px` + bg-tm-rule. */}
      <div className="grid grid-cols-2 gap-px bg-tm-rule md:grid-cols-4">
        <Kpi
          label={t(locale, "data.coverage.kTickers")}
          value={coverage.n_tickers.toString()}
        />
        <Kpi
          label={t(locale, "data.coverage.kDays")}
          value={coverage.n_days.toString()}
        />
        <Kpi
          label={t(locale, "data.coverage.kOhlcvPct")}
          value={`${coverage.ohlcv_coverage_pct.toFixed(2)}%`}
          tone={coverage.ohlcv_coverage_pct >= 99 ? "pos" : "warn"}
        />
        <Kpi
          label={t(locale, "data.coverage.kRange")}
          value={`${coverage.start_date} → ${coverage.end_date}`}
          mono
        />
      </div>

      {/* Per-field fill rate bars, grouped by category */}
      <div className="flex flex-col gap-3 border-t border-tm-rule px-3 py-3">
        {(["ohlcv", "metadata", "fundamental"] as const).map((cat) => {
          const fields = byCategory.get(cat);
          if (!fields || fields.length === 0) return null;
          return (
            <section key={cat}>
              <h3 className="mb-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
                {t(locale, CATEGORY_LABEL_KEY[cat])} ({fields.length})
              </h3>
              <div className="flex flex-col gap-1">
                {fields.map((f) => (
                  <FieldBar key={f.name} field={f} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {worstTickers.length > 0 && worstTickers[0].fill_rate < 1.0 && (
        <section className="border-t border-tm-rule px-3 py-3">
          <h3 className="mb-1.5 font-tm-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
            {t(locale, "data.coverage.worstTickers")}
          </h3>
          <div className="flex flex-col gap-1 font-tm-mono">
            {worstTickers
              .filter((tk) => tk.fill_rate < 1.0)
              .map((tk) => (
                <div
                  key={tk.ticker}
                  className="flex items-center gap-3 text-[11.5px]"
                >
                  <span className="w-20 text-tm-fg">{tk.ticker}</span>
                  <div className="relative h-3 flex-1 overflow-hidden border border-tm-rule bg-tm-bg-3">
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
                  <span className="w-20 text-right text-[11px] text-tm-muted">
                    {tk.n_missing} missing
                  </span>
                </div>
              ))}
          </div>
        </section>
      )}

      <p className="border-t border-tm-rule px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-muted">
        {t(locale, "data.coverage.legend")}
      </p>
    </TmPane>
  );
}

function FieldBar({ field }: { field: FieldCoverage }) {
  return (
    <div className="flex items-center gap-3 font-tm-mono text-[11.5px]">
      <code className="w-44 truncate text-tm-fg" title={field.name}>
        {field.name}
      </code>
      <div className="relative h-4 flex-1 overflow-hidden border border-tm-rule bg-tm-bg-3">
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
      <span className="w-24 text-right text-[11px] text-tm-muted">
        {field.n_present.toLocaleString()} / {field.n_total.toLocaleString()}
      </span>
    </div>
  );
}

interface KpiProps {
  readonly label: string;
  readonly value: string;
  readonly tone?: "pos" | "warn" | "neg";
  readonly mono?: boolean;
}

function Kpi({ label, value, tone, mono }: KpiProps) {
  const valueClass =
    tone === "pos"
      ? "text-tm-pos"
      : tone === "warn"
        ? "text-tm-warn"
        : tone === "neg"
          ? "text-tm-neg"
          : "text-tm-fg";
  return (
    <div className="flex flex-col gap-1 bg-tm-bg px-3 py-2.5 font-tm-mono">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-muted">
        {label}
      </div>
      <div
        className={`tabular-nums text-[15px] font-semibold ${valueClass} ${mono ? "" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}
