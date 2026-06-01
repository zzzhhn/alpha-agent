import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
import clsx from "clsx";
import WatchlistStar from "@/components/ui/WatchlistStar";
import GradeStrip from "./GradeStrip";
import { t, type Locale } from "@/lib/i18n";
// Reuse the app-wide signal→label map (also used by the stock-detail Radar
// and AttributionTable) so the drivers/drags column reads in plain language
// AND stays consistent with how the same signals are labeled elsewhere.
import { getSignalDisplayLabel } from "@/lib/signal-labels";

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
  const conf =
    typeof card.confidence === "number" && isFinite(card.confidence)
      ? card.confidence
      : 0;
  const sign = composite >= 0 ? "+" : "";

  // confidence = 1/(1+variance) of the signal z's (fusion/rating.py). Below
  // 0.5 the signal variance exceeds 1.0 — the contributing signals span more
  // than a full sigma, i.e. they disagree more than they agree. That is the
  // "scrutinize before acting" case, so flag it in tm-warn rather than
  // letting it blend into the ~57% board norm. The cutoff is the var=1
  // inflection of 1/(1+var), not an arbitrary line (rule 9 justification).
  const CONF_CAUTION = 0.5;
  const lowConf = conf < CONF_CAUTION;
  const confPct = Math.round(conf * 100);
  const confBar = lowConf ? "bg-tm-warn" : "bg-tm-fg-2/50";
  const confText = lowConf ? "text-tm-warn" : "text-tm-fg-2";

  const drivers = (card.top_drivers ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));
  const drags = (card.top_drags ?? [])
    .slice(0, 3)
    .map((s) => getSignalDisplayLabel(s, locale));

  return (
    <tr className="border-b border-tm-rule hover:bg-tm-bg-2 transition-colors">
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] text-tm-muted tabular-nums">
        {rank}
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[11px] font-semibold">
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
          <span
            className="ml-1 align-middle text-[10px] font-normal text-tm-warn"
            title={t(locale, "picks_table.tier_flip_tooltip")}
          >
            ⇄
          </span>
        ) : null}
        {card.partial ? (
          <span
            className="ml-1.5 rounded bg-tm-bg-2 px-1 py-0.5 align-middle text-[8px] font-semibold uppercase tracking-wide text-tm-muted"
            title={t(locale, "picks_table.partial_tooltip")}
          >
            {t(locale, "picks_table.partial_badge")}
          </span>
        ) : null}
        {staleDays > 0 ? (
          <span
            className="ml-1.5 rounded bg-tm-warn-soft px-1 py-0.5 align-middle text-[8px] font-semibold tabular-nums text-tm-warn"
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
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px]">
        <span
          className={clsx(
            "font-semibold",
            TIER_COLOR[card.rating] ?? "text-tm-fg-2",
          )}
        >
          {card.rating}
        </span>
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] tabular-nums text-right">
        {sign}
        {composite.toFixed(2)}
        <span className="text-tm-muted">σ</span>
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10.5px] tabular-nums">
        <span
          className="flex items-center justify-end gap-1.5"
          title={t(locale, "picks_table.confidence_tooltip")}
        >
          <span className="relative inline-block h-1 w-10 overflow-hidden rounded-sm bg-tm-rule">
            <span
              className={clsx("absolute inset-y-0 left-0 rounded-sm", confBar)}
              style={{ width: `${confPct}%` }}
            />
          </span>
          <span className={clsx("w-8 text-right", confText)}>{confPct}%</span>
        </span>
      </td>
      <td className="px-3 py-1.5">
        <GradeStrip grades={card.dimension_grades ?? {}} locale={locale} hidden={hiddenDims} />
      </td>
      <td className="px-3 py-1.5 font-tm-mono text-[10px]">
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
