"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { UniverseInfo } from "@/lib/types";

interface UniverseCardProps {
  readonly universe: UniverseInfo;
}

export function UniverseCard({ universe }: UniverseCardProps) {
  const { locale } = useLocale();
  return (
    <Card padding="md">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-text">{universe.name}</h3>
          <p className="mt-0.5 font-mono text-[12px] text-muted">{universe.id}</p>
        </div>
        <Badge variant="purple" size="sm">
          {universe.currency}
        </Badge>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] md:grid-cols-4">
        <Stat
          label={t(locale, "data.universe.tickerCount")}
          value={universe.ticker_count.toString()}
        />
        <Stat
          label={t(locale, "data.universe.benchmark")}
          value={universe.benchmark}
        />
        <Stat
          label={t(locale, "data.universe.days")}
          value={universe.n_days.toString()}
        />
        <Stat
          label={t(locale, "data.universe.range")}
          value={`${universe.start_date} → ${universe.end_date}`}
        />
      </dl>

      <details className="mt-3 border-t border-border pt-3">
        <summary className="cursor-pointer text-[13px] text-muted hover:text-text">
          {t(locale, "data.universe.tickersLabel")} ({universe.tickers.length})
        </summary>
        <div className="mt-2 flex flex-wrap gap-1">
          {universe.tickers.map((tk) => (
            <span
              key={tk}
              className="rounded bg-[var(--toggle-bg)] px-1.5 py-0.5 font-mono text-[12px] text-text"
            >
              {tk}
            </span>
          ))}
        </div>
      </details>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[12px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-sm text-text">{value}</dd>
    </div>
  );
}
