"use client";

import type { RatingCard, EarningsRaw } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

function decodeEarnings(raw: unknown): EarningsRaw | null {
  if (typeof raw !== "object" || raw === null) return null;
  return raw as EarningsRaw;
}

function decodeCalendar(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  return [];
}

function fmtCurrency(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

export default function CatalystsBlock({ card }: { card: RatingCard }) {
  const { locale } = useLocale();

  const earnings = decodeEarnings(card.breakdown.find((b) => b.signal === "earnings")?.raw);
  const calendar = decodeCalendar(card.breakdown.find((b) => b.signal === "calendar")?.raw);

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-4">
      <h2 className="text-lg font-semibold text-tm-fg">{t(locale, "catalysts.title")}</h2>

      {/* Earnings card */}
      <div>
        <div className="text-xs text-tm-muted uppercase tracking-wide mb-2">
          {t(locale, "catalysts.earnings_label")}
        </div>
        {earnings && earnings.next_date ? (
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <div className="text-tm-fg font-mono">{earnings.next_date}</div>
              <div className="text-xs text-tm-muted">
                {earnings.days_until != null
                  ? `${earnings.days_until} ${t(locale, "catalysts.days_until")}`
                  : ""}
              </div>
            </div>
            <div>
              <div className="text-xs text-tm-muted">{t(locale, "catalysts.eps_estimate")}</div>
              <div className="text-tm-fg font-mono">
                {earnings.eps_estimate != null ? earnings.eps_estimate.toFixed(2) : "—"}
              </div>
            </div>
            <div>
              <div className="text-xs text-tm-muted">{t(locale, "catalysts.revenue_estimate")}</div>
              <div className="text-tm-fg font-mono">{fmtCurrency(earnings.revenue_estimate)}</div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-tm-muted">{t(locale, "catalysts.no_earnings")}</p>
        )}
      </div>

      {/* Macro calendar */}
      <div>
        <div className="text-xs text-tm-muted uppercase tracking-wide mb-2">
          {t(locale, "catalysts.calendar_label")}
        </div>
        {calendar.length === 0 ? (
          <p className="text-sm text-tm-muted">{t(locale, "catalysts.no_calendar")}</p>
        ) : (
          <ul className="text-xs text-tm-fg-2 space-y-1">
            {calendar.slice(0, 5).map((evt, i) => (
              <li key={i} className="font-mono">
                {typeof evt === "string" ? evt : JSON.stringify(evt)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
