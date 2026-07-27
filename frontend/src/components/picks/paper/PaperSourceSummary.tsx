"use client";

import type { TickerAttribution } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

function money(value: number): string {
  return `${value >= 0 ? "+" : "-"}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function PaperSourceSummary({ rows }: { readonly rows: readonly TickerAttribution[] }) {
  const { locale } = useLocale();
  const groups = (["pick", "manual", "mixed"] as const).map((source) => {
    const matching = rows.filter((row) => row.source_type === source);
    return {
      source,
      count: matching.length,
      pnl: matching.reduce((sum, row) => sum + row.realized_pnl + row.unrealized_pnl, 0),
    };
  });
  const label = {
    pick: t(locale, "sim.workspace.source_pick"),
    manual: t(locale, "sim.workspace.source_manual"),
    mixed: t(locale, "sim.workspace.source_mixed"),
  } as const;

  return (
    <div className="border-t border-tm-rule">
      <div className="border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
        {t(locale, "sim.workspace.source_record")}
      </div>
      <div className="grid grid-cols-3 divide-x divide-tm-rule">
        {groups.map((group) => (
          <div key={group.source} className="px-3 py-2.5">
            <div className="font-tm-mono text-[9.5px] uppercase tracking-wide text-tm-muted">{label[group.source]}</div>
            <div className={`mt-1 font-tm-mono text-[16px] font-semibold tabular-nums ${group.pnl >= 0 ? "text-tm-pos" : "text-tm-neg"}`}>{money(group.pnl)}</div>
            <div className="mt-0.5 font-tm-mono text-[9.5px] text-tm-muted">{t(locale, "sim.workspace.tracked_tickers")} {group.count}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
