"use client";

// PaperAttributionTable — "按标的汇总" rollup fed by GET /api/paper/attribution.
// That endpoint lands from a parallel backend task; until it exists (or on any
// fetch failure) this renders an unobtrusive empty state rather than an error
// banner, per spec ("本地可先以空态渲染" — not a real failure to alarm on).
import type { TickerAttribution } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";

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
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-tm-rule">
            {COLS.map((k) => (
              <th
                key={k}
                className="px-3 py-1.5 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted text-right first:text-left"
              >
                {t(locale, k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticker} className="border-b border-tm-rule hover:bg-tm-bg-2">
              <td className="px-3 py-2 font-tm-mono text-[12px] font-semibold text-tm-accent">{r.ticker}</td>
              <td className={`px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right ${pnlTone(r.realized_pnl)}`}>
                {pnl(r.realized_pnl)}
              </td>
              <td className={`px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right ${pnlTone(r.unrealized_pnl)}`}>
                {pnl(r.unrealized_pnl)}
              </td>
              <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right text-tm-fg-2">
                {r.pick_linked_trades}
              </td>
              <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-right text-tm-fg-2">
                {r.self_directed_trades}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
