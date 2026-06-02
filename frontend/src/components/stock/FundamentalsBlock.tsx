"use client";

import type { RatingCard, FactorRaw, FundamentalsData } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { InfoTooltip } from "@/components/ui/InfoTooltip";

function decodeFactorRaw(raw: unknown): FundamentalsData | null {
  // Pre-M4a rows had factor.raw = float (the z score). Tolerate that by
  // checking shape before reading nested fields.
  if (typeof raw !== "object" || raw === null) return null;
  const obj = raw as Partial<FactorRaw>;
  return obj.fundamentals ?? null;
}

function fmtNumber(v: number | null, digits = 2): string {
  if (v == null) return "—";
  return v.toFixed(digits);
}

// profit_margin is a yfinance RATIO (0.0226) → ×100 for display.
function fmtPercent(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

// dividend_yield arrives ALREADY in percent units from current yfinance
// (dividendYield returns 2.18 meaning 2.18%, not the old 0.0218 ratio). Do
// NOT ×100 — that double-scale was the "218%" P0-2 bug. Kept distinct from
// fmtPercent so the two yfinance conventions don't get conflated again.
function fmtPercentRaw(v: number | null): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

function fmtCurrency(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

// Plausible ranges in each field's RAW backend units. A value outside its
// range is almost certainly an upstream data error (unit drift, yfinance
// junk for a given ticker); we hide it behind "—" + a tooltip rather than
// present it as fact, because one absurd number (a 218% yield, a negative
// P/E) destroys the page's credibility for any user who knows stocks.
// NOTE: this catches gross anomalies, not subtly-wrong-but-in-range values
// (e.g. a stale yfinance trailingEps); those need a backend price cross-check.
const SANITY_BOUNDS: Partial<Record<keyof FundamentalsData, readonly [number, number]>> = {
  pe_trailing: [0.5, 500],
  pe_forward: [0.5, 500],
  eps_ttm: [-50, 500],
  dividend_yield: [0, 25], // percent units
  profit_margin: [-1, 0.6], // ratio units
  debt_to_equity: [0, 2000],
  beta: [-3, 5],
};

function withinBounds(field: keyof FundamentalsData, v: number | null): boolean {
  if (v == null) return true; // null already renders as "—" via the formatter
  const b = SANITY_BOUNDS[field];
  if (!b) return true;
  return v >= b[0] && v <= b[1];
}

export default function FundamentalsBlock({ card }: { card: RatingCard }) {
  const { locale } = useLocale();

  const factor = card.breakdown.find((b) => b.signal === "factor");
  const fund = decodeFactorRaw(factor?.raw);

  if (!fund) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "fundamentals.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "fundamentals.empty")}</p>
      </section>
    );
  }

  const fields: {
    field: keyof FundamentalsData;
    labelKey: Parameters<typeof t>[1];
    fmt: (v: number | null) => string;
  }[] = [
    { field: "pe_trailing", labelKey: "fundamentals.pe_trailing", fmt: (v) => fmtNumber(v) },
    { field: "pe_forward", labelKey: "fundamentals.pe_forward", fmt: (v) => fmtNumber(v) },
    { field: "eps_ttm", labelKey: "fundamentals.eps_ttm", fmt: (v) => fmtNumber(v) },
    { field: "market_cap", labelKey: "fundamentals.market_cap", fmt: fmtCurrency },
    { field: "dividend_yield", labelKey: "fundamentals.dividend_yield", fmt: fmtPercentRaw },
    { field: "profit_margin", labelKey: "fundamentals.profit_margin", fmt: fmtPercent },
    { field: "debt_to_equity", labelKey: "fundamentals.debt_to_equity", fmt: (v) => fmtNumber(v, 1) },
    { field: "beta", labelKey: "fundamentals.beta", fmt: (v) => fmtNumber(v) },
  ];

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "fundamentals.title")}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {fields.map((c) => {
          const raw = fund[c.field];
          const ok = withinBounds(c.field, raw);
          return (
            <div key={c.labelKey} className="space-y-0.5">
              <div className="flex items-center gap-1 text-xs text-tm-muted uppercase tracking-wide">
                {t(locale, c.labelKey)}
                <InfoTooltip
                  iconSize={11}
                  content={t(
                    locale,
                    `fundamentals.tip_${c.field}` as Parameters<typeof t>[1],
                  )}
                />
              </div>
              {ok ? (
                <div className="text-base font-mono text-tm-fg">{c.fmt(raw)}</div>
              ) : (
                <div
                  className="text-base font-mono text-tm-warn cursor-help"
                  title={`${t(locale, "fundamentals.anomaly")} (${raw})`}
                >
                  ⚠ —
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
