"use client";

import type { RatingCard, FactorRaw, FundamentalsData } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

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

function fmtPercent(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function fmtCurrency(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
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

  const cells: { labelKey: Parameters<typeof t>[1]; value: string }[] = [
    { labelKey: "fundamentals.pe_trailing", value: fmtNumber(fund.pe_trailing) },
    { labelKey: "fundamentals.pe_forward", value: fmtNumber(fund.pe_forward) },
    { labelKey: "fundamentals.eps_ttm", value: fmtNumber(fund.eps_ttm) },
    { labelKey: "fundamentals.market_cap", value: fmtCurrency(fund.market_cap) },
    { labelKey: "fundamentals.dividend_yield", value: fmtPercent(fund.dividend_yield) },
    { labelKey: "fundamentals.profit_margin", value: fmtPercent(fund.profit_margin) },
    { labelKey: "fundamentals.debt_to_equity", value: fmtNumber(fund.debt_to_equity, 1) },
    { labelKey: "fundamentals.beta", value: fmtNumber(fund.beta) },
  ];

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "fundamentals.title")}
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cells.map((c) => (
          <div key={c.labelKey} className="space-y-0.5">
            <div className="text-xs text-tm-muted uppercase tracking-wide">
              {t(locale, c.labelKey)}
            </div>
            <div className="text-base font-mono text-tm-fg">{c.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
