import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import clsx from "clsx";
import WatchlistStar from "@/components/ui/WatchlistStar";
import { HoverTip } from "@/components/ui/HoverTip";
import GradeStrip from "./GradeStrip";
import { t, type Locale } from "@/lib/i18n";
// Reuse the app-wide signal→label map (also used by the stock-detail Radar
// and AttributionTable) so the drivers/drags column reads in plain language
// AND stays consistent with how the same signals are labeled elsewhere.
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { getSuggestion } from "@/lib/suggestion";

const TIER_COLOR: Record<string, string> = {
  BUY: "text-tm-pos",
  OW: "text-tm-pos",
  HOLD: "text-tm-fg-2",
  UW: "text-tm-neg",
  SELL: "text-tm-neg",
};

export default function PickRow({
  rank,
  card,
  watched = false,
  locale = "zh",
  hiddenDims,
  freshestAsOf,
}: {
  rank: number;
  card: RatingCard;
  watched?: boolean;
  locale?: Locale;
  hiddenDims?: ReadonlySet<string>;
  // Freshest as_of across the visible list, so a row that lags it (its own
  // data is from an earlier day) is flagged — the list header alone shows the
  // max, which would otherwise hide a stale row behind a fresh-looking time.
  freshestAsOf?: string | null;
}) {
  // Days this row's data lags the freshest row in the list (0 if within ~20h).
  const staleDays = (() => {
    if (!freshestAsOf || !card.as_of) return 0;
    const gap = new Date(freshestAsOf).getTime() - new Date(card.as_of).getTime();
    if (isNaN(gap) || gap <= 0) return 0;
    return gap > 20 * 3_600_000 ? Math.round(gap / 86_400_000) : 0;
  })();
  // Defensive: backend may return null for composite/confidence when legacy
  // DB rows held NaN before storage sanitization landed.
  const composite =
    typeof card.composite_score === "number" && isFinite(card.composite_score)
      ? card.composite_score
      : 0;
  const hit =
    typeof card.confidence === "number" && isFinite(card.confidence)
      ? card.confidence
      : 0;
  // agreement is the conviction headline; fall back to the calibrated value
  // only on legacy rows that predate the field so the bar is never blank.
  const agr =
    typeof card.agreement === "number" &&
    isFinite(card.agreement) &&
    card.agreement > 0
      ? card.agreement
      : hit;
  const sign = composite >= 0 ? "+" : "";

  // agreement = 1/(1+variance) of the signal z's (fusion/rating.py): the
  // conviction headline (how aligned the signals are). hit = calibrated
  // historical 5d hit-rate. Both moved into the consistency cell's tooltip now
  // that the column itself shows the multi-window directional hit-rate.
  const agrPct = Math.round(agr * 100);
  const hitPct = Math.round(hit * 100);

  // Directional consistency: predicted tier vs next-day actual move, hit-rate
  // over trailing windows. null -> "—" (insufficient realized history). Colour
  // only clearly-off-coinflip values (>=55 / <=45 around the structural ~50%);
  // the rest stay neutral so noisy near-50% reads do not over-claim an edge.
  const CONS_WINDOWS = [
    { key: "d5", labelKey: "picks_table.cons_5d" },
    { key: "m1", labelKey: "picks_table.cons_1m" },
    { key: "y1", labelKey: "picks_table.cons_1y" },
    { key: "hist", labelKey: "picks_table.cons_hist" },
  ] as const;
  const consVals = CONS_WINDOWS.map((w) => {
    const v = card.consistency?.[w.key];
    const ok = typeof v === "number" && isFinite(v);
    return { label: t(locale, w.labelKey), pct: ok ? Math.round(v * 100) : null };
  });

  const drivers = (card.top_drivers ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));
  const drags = (card.top_drags ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));

  return (
    <tr className="border-b border-tm-rule hover:bg-tm-bg-2 transition-colors">
      <td className="px-3 py-2.5 font-tm-mono text-xs text-tm-muted tabular-nums">
        {rank}
      </td>
      <td className="px-3 py-2.5 font-tm-mono text-[13px] font-semibold">
        {watched ? (
          <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" />
        ) : null}
        <Link
          href={`/stock/${card.ticker}`}
          className="text-tm-accent hover:underline"
        >
          {card.ticker}
        </Link>
        {card.tier_flip_today ? (
          <HoverTip
            content={t(locale, "picks_table.tier_flip_tooltip")}
            placement="bottom"
            className="ml-1 align-middle"
          >
            <span className="cursor-help text-[11px] font-normal text-tm-warn">
              ⇄
            </span>
          </HoverTip>
        ) : null}
        {card.partial ? (
          <span
            className="ml-1.5 rounded bg-tm-bg-2 px-1 py-0.5 align-middle text-[11px] font-semibold uppercase tracking-wide text-tm-muted"
            title={t(locale, "picks_table.partial_tooltip")}
          >
            {t(locale, "picks_table.partial_badge")}
          </span>
        ) : null}
        {staleDays > 0 ? (
          <span
            className="ml-1.5 rounded bg-tm-warn-soft px-1 py-0.5 align-middle text-[11px] font-semibold tabular-nums text-tm-warn"
            title={
              locale === "zh"
                ? `该行数据比榜单最新时间旧 ${staleDays} 天`
                : `this row's data is ${staleDays}d older than the freshest`
            }
          >
            {staleDays}d
          </span>
        ) : null}
      </td>
      <td className="px-3 py-2.5 font-tm-mono text-xs">
        <span
          className={clsx(
            "font-semibold",
            TIER_COLOR[card.rating] ?? "text-tm-fg-2",
          )}
        >
          {card.rating}
        </span>
      </td>
      <td className="px-3 py-2.5 text-[13px]">
        {(() => {
          const sug = getSuggestion(card.rating, hit, locale);
          const tone =
            sug.tone === "pos"
              ? "text-tm-pos"
              : sug.tone === "neg"
                ? "text-tm-neg"
                : "text-tm-fg-2";
          // Caution: the action stands (the model's tier), but the modest
          // realized edge is disclosed rather than hidden — dimmed + a warn
          // marker that explains the ~coin-flip hit-rate on hover.
          return sug.caution ? (
            <HoverTip content={t(locale, "picks_table.sug_caution_tip")} placement="bottom">
              <span className={clsx("font-semibold opacity-60", tone)}>{sug.label}</span>
              <span className="ml-0.5 cursor-help text-tm-warn">⚠</span>
            </HoverTip>
          ) : (
            <span className={clsx("font-semibold", tone)}>{sug.label}</span>
          );
        })()}
      </td>
      <td className="px-3 py-2.5 font-tm-mono text-xs tabular-nums text-right">
        {sign}
        {composite.toFixed(2)}
        <span className="text-tm-muted">σ</span>
      </td>
      <td className="px-3 py-2.5 font-tm-mono text-[11px] tabular-nums">
        <HoverTip
          content={
            t(locale, "picks_table.consistency_tooltip") +
            " · " +
            t(locale, "picks_table.agreement_label") +
            " " +
            agrPct +
            "% · " +
            t(locale, "picks_table.hitrate_label") +
            " " +
            hitPct +
            "%"
          }
          placement="bottom"
        >
          <span className="grid grid-cols-4 gap-x-1.5 text-right cursor-help">
            {consVals.map((c) => (
              <span key={c.label} className="text-[10px] text-tm-muted">
                {c.label}
              </span>
            ))}
            {consVals.map((c) => (
              <span
                key={c.label + "_v"}
                className={clsx(
                  "tabular-nums",
                  c.pct === null
                    ? "text-tm-muted"
                    : c.pct >= 55
                      ? "text-tm-pos"
                      : c.pct <= 45
                        ? "text-tm-neg"
                        : "text-tm-fg-2",
                )}
              >
                {c.pct === null ? "—" : `${c.pct}%`}
              </span>
            ))}
          </span>
        </HoverTip>
      </td>
      <td className="px-3 py-2.5">
        <GradeStrip grades={card.dimension_grades ?? {}} locale={locale} hidden={hiddenDims} />
      </td>
      <td className="px-3 py-2.5 font-tm-sans text-[12px]">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {drivers.length > 0 ? (
            <span className="text-tm-pos">
              ↑ {drivers.join(" ")}
            </span>
          ) : null}
          {drags.length > 0 ? (
            <span className="text-tm-neg">
              ↓ {drags.join(" ")}
            </span>
          ) : null}
          {drivers.length === 0 && drags.length === 0 ? (
            <span className="text-tm-muted">—</span>
          ) : null}
        </span>
      </td>
    </tr>
  );
}
