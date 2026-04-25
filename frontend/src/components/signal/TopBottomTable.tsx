"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { SignalTodayResponse } from "@/lib/types";

interface TopBottomTableProps {
  readonly today: SignalTodayResponse | null;
  readonly loading: boolean;
}

export function TopBottomTable({ today, loading }: TopBottomTableProps) {
  const { locale } = useLocale();
  return (
    <Card padding="md">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text">
            {t(locale, "signal.today.title")}
          </h2>
          {today && (
            <p className="mt-0.5 text-[10px] text-muted">
              {t(locale, "signal.today.asOf")}: <span className="font-mono">{today.as_of}</span>
              {" · "}universe {today.n_valid}/{today.universe_size}
            </p>
          )}
        </div>
      </header>

      {loading && <p className="py-6 text-center text-[11px] text-muted">…</p>}
      {!loading && !today && (
        <p className="py-6 text-center text-[11px] text-muted">
          {t(locale, "signal.today.empty")}
        </p>
      )}
      {today && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Side
            title={t(locale, "signal.today.long")}
            rows={today.top}
            variant="green"
            locale={locale}
          />
          <Side
            title={t(locale, "signal.today.short")}
            rows={today.bottom}
            variant="red"
            locale={locale}
          />
        </div>
      )}
    </Card>
  );
}

function Side({
  title, rows, variant, locale,
}: {
  title: string;
  rows: SignalTodayResponse["top"];
  variant: "green" | "red";
  locale: "zh" | "en";
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <Badge variant={variant} size="sm">{title}</Badge>
        <span className="text-[10px] text-muted">{rows.length}</span>
      </div>
      <div className="overflow-hidden rounded-md border border-border">
        <table className="w-full text-[11px]">
          <thead className="bg-[var(--toggle-bg)]">
            <tr>
              <th className="px-2 py-1 text-left font-medium text-muted">{t(locale, "signal.today.tickerCol")}</th>
              <th className="px-2 py-1 text-right font-medium text-muted">{t(locale, "signal.today.factorVal")}</th>
              <th className="px-2 py-1 text-left font-medium text-muted">{t(locale, "signal.today.sectorCol")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ticker} className="border-t border-border">
                <td className="px-2 py-1 font-mono font-semibold text-text">{r.ticker}</td>
                <td className="px-2 py-1 text-right font-mono text-text">{r.factor.toFixed(3)}</td>
                <td className="px-2 py-1 text-muted">{r.sector ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
