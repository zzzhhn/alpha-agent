"use client";

import clsx from "clsx";
import type { PositionOut, TickerAttribution } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

function sourceLabel(source: TickerAttribution["source_type"] | undefined, locale: "zh" | "en") {
  if (source === "pick") return t(locale, "sim.workspace.source_pick");
  if (source === "mixed") return t(locale, "sim.workspace.source_mixed");
  return t(locale, "sim.workspace.source_manual");
}

export default function PaperPositionsWithSource({
  positions,
  attribution,
}: {
  readonly positions: readonly PositionOut[];
  readonly attribution: readonly TickerAttribution[];
}) {
  const { locale } = useLocale();
  const sourceByTicker = new Map(attribution.map((row) => [row.ticker, row]));

  if (positions.length === 0) {
    return (
      <p className="px-3 py-8 font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "sim.overview.empty_hint")}
      </p>
    );
  }

  const headers = [
    t(locale, "sim.attribution.col_ticker"),
    t(locale, "sim.workspace.qty"),
    t(locale, "sim.workspace.avg_cost"),
    t(locale, "sim.workspace.current_value"),
    t(locale, "sim.workspace.pnl"),
    t(locale, "sim.workspace.source"),
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead className="bg-tm-bg-2">
          <tr className="border-b border-tm-rule">
            {headers.map((header, index) => (
              <th
                key={header}
                className={clsx(
                  "px-3 py-2 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted",
                  index > 0 && index < 5 && "text-right",
                )}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const source = sourceByTicker.get(position.ticker);
            const pnlPositive = position.unrealized_pnl >= 0;
            const currentValue = position.current_price === null
              ? null
              : position.current_price * position.qty;
            return (
              <tr key={position.ticker} className="border-b border-tm-rule hover:bg-tm-bg-2">
                <td className="px-3 py-2.5 font-tm-mono text-[12px] font-semibold text-tm-accent">{position.ticker}</td>
                <td className="px-3 py-2.5 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg-2">{position.qty.toLocaleString()}</td>
                <td className="px-3 py-2.5 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg-2">${position.avg_cost.toFixed(2)}</td>
                <td className="px-3 py-2.5 text-right font-tm-mono text-[11px] tabular-nums text-tm-fg-2">{currentValue === null ? "—" : `$${currentValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}</td>
                <td className={clsx("px-3 py-2.5 text-right font-tm-mono text-[11px] font-semibold tabular-nums", pnlPositive ? "text-tm-pos" : "text-tm-neg")}>{pnlPositive ? "+" : "-"}${Math.abs(position.unrealized_pnl).toLocaleString(undefined, { maximumFractionDigits: 0 })}<span className="ml-1 font-normal">({position.unrealized_pct >= 0 ? "+" : ""}{position.unrealized_pct.toFixed(2)}%)</span></td>
                <td className="px-3 py-2.5">
                  <span className={clsx(
                    "border px-1.5 py-0.5 font-tm-mono text-[9.5px] uppercase tracking-wide",
                    source?.source_type === "pick" ? "border-tm-accent text-tm-accent" : "border-tm-rule text-tm-fg-2",
                  )}>{sourceLabel(source?.source_type, locale)}</span>
                  {source?.latest_pick_date ? <span className="ml-2 font-tm-mono text-[9px] text-tm-muted">{source.latest_pick_date}</span> : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="px-3 py-2 font-tm-mono text-[9.5px] leading-4 text-tm-muted">
        {t(locale, "sim.workspace.source_note")}
      </p>
    </div>
  );
}
