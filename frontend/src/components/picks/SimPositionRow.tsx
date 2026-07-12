// frontend/src/components/picks/SimPositionRow.tsx
import clsx from "clsx";
import type { PositionOut } from "@/lib/api/paper";
import type { Locale } from "@/lib/i18n";

export default function SimPositionRow({
  pos,
  locale,
}: {
  readonly pos: PositionOut;
  readonly locale: Locale;
}) {
  // locale used for future localization of number formatting
  void locale;
  const pnlPos = pos.unrealized_pnl >= 0;
  const pctStr = pos.unrealized_pct >= 0
    ? `+${pos.unrealized_pct.toFixed(2)}%`
    : `${pos.unrealized_pct.toFixed(2)}%`;
  const pnlStr = pos.unrealized_pnl >= 0
    ? `+$${pos.unrealized_pnl.toFixed(0)}`
    : `-$${Math.abs(pos.unrealized_pnl).toFixed(0)}`;

  return (
    <tr className="border-b border-tm-rule hover:bg-tm-bg-2 transition-colors">
      <td className="px-3 py-2 font-tm-mono text-[12px] font-semibold text-tm-accent">
        {pos.ticker}
      </td>
      <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2 text-right">
        {pos.qty.toLocaleString()}
      </td>
      <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2 text-right">
        ${pos.avg_cost.toFixed(2)}
      </td>
      <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2 text-right">
        {pos.current_price !== null ? `$${pos.current_price.toFixed(2)}` : "—"}
      </td>
      <td className={clsx(
        "px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right font-semibold",
        pnlPos ? "text-tm-pos" : "text-tm-neg",
      )}>
        {pnlStr}
      </td>
      <td className={clsx(
        "px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right",
        pnlPos ? "text-tm-pos" : "text-tm-neg",
      )}>
        {pctStr}
      </td>
    </tr>
  );
}
