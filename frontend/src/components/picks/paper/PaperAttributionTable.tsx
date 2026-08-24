"use client";

// PaperAttributionTable — "按标的汇总" rollup fed by GET /api/paper/attribution.
// That endpoint lands from a parallel backend task; until it exists (or on any
// fetch failure) this renders an unobtrusive empty state rather than an error
// banner, per spec ("本地可先以空态渲染" — not a real failure to alarm on).
import type { TickerAttribution } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const pnl = (n: number) => `${n >= 0 ? "+" : ""}$${FMT.format(Math.abs(n))}`;
const pnlTone = (n: number) => (n >= 0 ? "text-tm-pos" : "text-tm-neg");

const COLS: readonly TranslationKey[] = [
  "sim.attribution.col_ticker",
  "sim.attribution.col_realized",
  "sim.attribution.col_unrealized",
  "sim.attribution.col_followed",
  "sim.attribution.col_manual",
];

export default function PaperAttributionTable({
  rows,
  status,
}: {
  readonly rows: readonly TickerAttribution[];
  readonly status: "loading" | "ready" | "unavailable";
}) {
  const { locale } = useLocale();

  if (status === "unavailable") {
    return (
      <p className="font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "sim.attribution.unavailable")}
      </p>
    );
  }
  if (status === "loading") {
    return <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.loading")}</p>;
  }
  if (rows.length === 0) {
    return <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "sim.attribution.empty")}</p>;
  }

  return (
    <TmTableFrame>
      <TmTable density="compact" caption={t(locale, "sim.attribution.title")} className="text-left">
        <TmTableHead>
          <TmTableRow>
            {COLS.map((k, index) => (
              <TmTableHeaderCell key={k} textAlign={index === 0 ? "left" : "right"} className="text-[10px] tracking-wide">
                {t(locale, k)}
              </TmTableHeaderCell>
            ))}
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {rows.map((r) => (
            <TmTableRow key={r.ticker}>
              <TmTableRowHeader className="text-[12px] font-semibold text-tm-accent">{r.ticker}</TmTableRowHeader>
              <TmTableCell numeric textAlign="right" className={`text-[11px] ${pnlTone(r.realized_pnl)}`}>
                {pnl(r.realized_pnl)}
              </TmTableCell>
              <TmTableCell numeric textAlign="right" className={`text-[11px] ${pnlTone(r.unrealized_pnl)}`}>
                {pnl(r.unrealized_pnl)}
              </TmTableCell>
              <TmTableCell numeric textAlign="right" className="text-[11px] text-tm-fg-2">
                {r.pick_linked_trades}
              </TmTableCell>
              <TmTableCell numeric textAlign="right" className="text-[11px] text-tm-fg-2">
                {r.self_directed_trades}
              </TmTableCell>
            </TmTableRow>
          ))}
        </TmTableBody>
      </TmTable>
    </TmTableFrame>
  );
}
