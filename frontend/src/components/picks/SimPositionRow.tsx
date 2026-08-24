// frontend/src/components/picks/SimPositionRow.tsx
import clsx from "clsx";
import type { PositionOut } from "@/lib/api/paper";
import type { Locale } from "@/lib/i18n";
import {
  TmTableCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

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
    <TmTableRow>
      <TmTableRowHeader className="text-[12px] font-semibold text-tm-accent">
        {pos.ticker}
      </TmTableRowHeader>
      <TmTableCell numeric textAlign="right" className="text-[11px] text-tm-fg-2">
        {pos.qty.toLocaleString()}
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className="text-[11px] text-tm-fg-2">
        ${pos.avg_cost.toFixed(2)}
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className="text-[11px] text-tm-fg-2">
        {pos.current_price !== null ? `$${pos.current_price.toFixed(2)}` : "—"}
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className={clsx(
        "text-[11px] font-semibold",
        pnlPos ? "text-tm-pos" : "text-tm-neg",
      )}>
        {pnlStr}
      </TmTableCell>
      <TmTableCell numeric textAlign="right" className={clsx(
        "text-[11px]",
        pnlPos ? "text-tm-pos" : "text-tm-neg",
      )}>
        {pctStr}
      </TmTableCell>
    </TmTableRow>
  );
}
