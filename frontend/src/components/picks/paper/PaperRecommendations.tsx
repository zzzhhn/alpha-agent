"use client";

import clsx from "clsx";
import type { RatingCard } from "@/lib/api/picks";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";

const TIER_TONE: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

function pct(value: number | null | undefined): string {
  if (typeof value !== "number" || !isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function PaperRecommendations({
  picks,
  selectedTicker,
  actionable,
  onSelect,
}: {
  readonly picks: readonly RatingCard[];
  readonly selectedTicker: string | null;
  readonly actionable: boolean;
  readonly onSelect: (pick: RatingCard) => void;
}) {
  const { locale } = useLocale();

  if (picks.length === 0) {
    return (
      <p className="px-3 py-8 font-tm-mono text-[11px] text-tm-muted">
        {t(locale, "sim.workspace.no_picks")}
      </p>
    );
  }

  return (
    <>
      <div className="divide-y divide-tm-rule sm:hidden">
        {picks.map((pick) => {
          const selected = selectedTicker === pick.ticker;
          const company = locale === "zh"
            ? pick.company_name_zh ?? pick.company_name
            : pick.company_name;
          const confidence = pick.agreement ?? pick.confidence;
          const rationale = (pick.top_drivers ?? [])
            .slice(0, 2)
            .map((name) => getSignalDisplayLabel(name, locale))
            .join(" · ");
          return (
            <article
              key={pick.ticker}
              className={clsx(
                "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 px-3 py-3",
                selected && "bg-tm-accent-soft outline outline-1 -outline-offset-1 outline-tm-accent",
              )}
            >
              <div className="min-w-0">
                <div className="truncate text-[12px] text-tm-fg">{company ?? pick.ticker}</div>
                <div className="font-tm-mono text-[11px] font-semibold text-tm-accent">{pick.ticker}</div>
              </div>
              <div className="text-right">
                <div className={clsx("font-tm-mono text-[11px] font-semibold", TIER_TONE[pick.rating] ?? "text-tm-fg-2")}>{pick.rating}</div>
                <div className={clsx("font-tm-mono text-[10px] tabular-nums", (pick.daily_change_pct ?? 0) >= 0 ? "text-tm-pos" : "text-tm-neg")}>{pct(pick.daily_change_pct)}</div>
              </div>
              <div className="font-tm-mono text-[11px] text-tm-fg-2">
                {typeof pick.latest_price === "number" ? `$${pick.latest_price.toFixed(2)}` : "—"}
                <span className="ml-2 text-[9px] text-tm-muted">{pick.price_date ?? "—"}</span>
              </div>
              <div className="font-tm-mono text-[10px] text-tm-muted">
                {typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "—"}
              </div>
              <div className="min-w-0 truncate text-[10px] text-tm-muted">{rationale || "—"}</div>
              <TmButton variant="secondary" className="px-2 py-1" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                {t(locale, "sim.workspace.follow")}
              </TmButton>
            </article>
          );
        })}
      </div>
      <div className="hidden overflow-x-auto sm:block">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <thead className="bg-tm-bg-2">
          <tr className="border-b border-tm-rule">
            {[t(locale, "sim.workspace.company_ticker"), t(locale, "sim.form.side_label"), t(locale, "sim.workspace.latest_close"), t(locale, "sim.workspace.day_change"), t(locale, "sim.workspace.confidence"), t(locale, "sim.workspace.rationale"), ""].map((label) => (
              <th
                key={label || "action"}
                className="px-3 py-2 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted"
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {picks.map((pick) => {
            const selected = selectedTicker === pick.ticker;
            const company = locale === "zh"
              ? pick.company_name_zh ?? pick.company_name
              : pick.company_name;
            const confidence = pick.agreement ?? pick.confidence;
            const rationale = (pick.top_drivers ?? [])
              .slice(0, 2)
              .map((name) => getSignalDisplayLabel(name, locale))
              .join(" · ");
            return (
              <tr
                key={pick.ticker}
                className={clsx(
                  "border-b border-tm-rule transition-colors",
                  selected ? "bg-tm-accent-soft outline outline-1 -outline-offset-1 outline-tm-accent" : "hover:bg-tm-bg-2",
                )}
              >
                <td className="px-3 py-2.5">
                  <div className="text-[12px] text-tm-fg">{company ?? pick.ticker}</div>
                  <div className="font-tm-mono text-[11px] font-semibold text-tm-accent">{pick.ticker}</div>
                </td>
                <td className={clsx("px-3 py-2.5 font-tm-mono text-[11px] font-semibold", TIER_TONE[pick.rating] ?? "text-tm-fg-2")}>{pick.rating}</td>
                <td className="px-3 py-2.5 font-tm-mono text-[11px] tabular-nums text-tm-fg-2">
                  {typeof pick.latest_price === "number" ? `$${pick.latest_price.toFixed(2)}` : "—"}
                  {pick.price_date ? <span className="block text-[9px] text-tm-muted">{pick.price_date}</span> : null}
                </td>
                <td className={clsx(
                  "px-3 py-2.5 font-tm-mono text-[11px] tabular-nums",
                  (pick.daily_change_pct ?? 0) >= 0 ? "text-tm-pos" : "text-tm-neg",
                )}>{pct(pick.daily_change_pct)}</td>
                <td className="px-3 py-2.5 font-tm-mono text-[11px] tabular-nums text-tm-fg-2">
                  {typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : "—"}
                </td>
                <td className="max-w-48 px-3 py-2.5 text-[11px] leading-4 text-tm-muted">{rationale || "—"}</td>
                <td className="px-3 py-2.5 text-right">
                  <TmButton variant="secondary" disabled={!actionable} onClick={() => onSelect(pick)} aria-pressed={selected}>
                    {t(locale, "sim.workspace.follow")}
                  </TmButton>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </>
  );
}
