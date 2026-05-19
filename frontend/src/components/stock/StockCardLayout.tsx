"use client";

import Link from "next/link";
import type { GexInfo, RatingCard } from "@/lib/api/picks";
import type { Locale } from "@/lib/i18n";
import LetterGradeRibbon from "./LetterGradeRibbon";
import PersonaPanel from "./PersonaPanel";
import { useWatchlist } from "@/hooks/useWatchlist";
import WatchlistStar from "@/components/ui/WatchlistStar";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import RatingBadge from "./RatingBadge";
import ActionBox from "./ActionBox";
import LeanThesis from "./LeanThesis";
import RichThesis from "./RichThesis";
import AttributionRadar from "./AttributionRadar";
import AttributionTable from "./AttributionTable";
import PriceChart from "./PriceChart";
import FundamentalsBlock from "./FundamentalsBlock";
import CatalystsBlock from "./CatalystsBlock";
import NewsBlock from "./NewsBlock";
import MarketContextWidget from "./MarketContextWidget";
import SourcesBlock from "./SourcesBlock";

export default function StockCardLayout({
  card,
  stale,
}: {
  card: RatingCard;
  stale: boolean;
}) {
  const { isWatched } = useWatchlist();
  const watched = isWatched(card.ticker);
  const { locale } = useLocale();
  return (
    <div className="grid grid-cols-12 gap-6 px-4 py-6">
      {/* Left rail (sticky) */}
      <aside className="col-span-3 sticky top-4 self-start space-y-4">
        {/* Back-to-picks: small affordance because direct URL access (e.g. */}
        {/* shared link) leaves no history entry → router.back() would no-op. */}
        <Link
          href="/picks"
          className="inline-flex items-center gap-1 text-xs text-tm-muted hover:text-tm-accent"
        >
          <span aria-hidden="true">←</span>
          <span>{t(locale, "stock_layout.back_to_picks")}</span>
        </Link>
        <div
          className={`flex items-center gap-1.5 text-2xl font-bold ${watched ? "text-tm-accent" : "text-tm-fg"}`}
        >
          {watched ? <WatchlistStar className="h-5 w-5 text-tm-accent" /> : null}
          <span>{card.ticker}</span>
        </div>
        <RatingBadge
          rating={card.rating}
          confidence={card.confidence}
          composite={card.composite_score}
        />
        {card.gex_info ? (
          <GexBadge info={card.gex_info} locale={locale} />
        ) : null}
        {card.dimension_grades && Object.keys(card.dimension_grades).length > 0 ? (
          <LetterGradeRibbon grades={card.dimension_grades} locale={locale} />
        ) : null}
        <ActionBox card={card} />
        <div className="text-xs text-tm-muted space-y-0.5">
          <div>{t(locale, "stock_layout.as_of")} {new Date(card.as_of).toLocaleString()}</div>
          {stale ? (
            <div className="rounded bg-tm-warn-soft px-2 py-1 text-tm-warn">
              ⚠ {t(locale, "stock_layout.stale_warning")}
            </div>
          ) : null}
          {card.partial ? (
            <div className="rounded bg-tm-bg-2 px-2 py-1 text-tm-muted">
              {t(locale, "stock_layout.partial_data")}
            </div>
          ) : null}
        </div>
      </aside>

      {/* Right scroll */}
      <main className="col-span-9 space-y-8">
        <LeanThesis card={card} />
        <RichThesis ticker={card.ticker} />
        <section>
          <h2 className="text-lg font-semibold mb-3 text-tm-fg">{t(locale, "stock_layout.signal_attribution")}</h2>
          <div className="grid grid-cols-12 gap-4">
            <div className="col-span-4">
              <AttributionRadar card={card} />
            </div>
            <div className="col-span-8">
              <AttributionTable card={card} />
            </div>
          </div>
        </section>
        <PersonaPanel ticker={card.ticker} />
        <PriceChart ticker={card.ticker} />
        <FundamentalsBlock card={card} />
        <CatalystsBlock card={card} />
        <NewsBlock card={card} />
        <MarketContextWidget ticker={card.ticker} />
        <SourcesBlock card={card} />
      </main>
    </div>
  );
}


/**
 * B5 GEX regime pill. Three states:
 *   pinned   (signed_notional > +band) — dealers net-long gamma, "buy
 *            weakness / sell strength", low realized vol expected;
 *            green pill, signals "buy-the-dip works today".
 *   volatile (signed_notional < −band) — dealers net-short gamma,
 *            "buy strength / sell weakness", trend continuation;
 *            warn pill, signals "trend day, avoid mean reversion".
 *   mixed    (within ±band) — neutral, no actionable regime signal.
 *
 * Notional rendered in $B / $M depending on magnitude for legibility.
 */
function GexBadge({ info, locale }: { info: GexInfo; locale: Locale }) {
  const absNotional = Math.abs(info.signed_notional);
  const fmtNotional =
    absNotional >= 1e9
      ? `${(info.signed_notional / 1e9).toFixed(1)}B`
      : absNotional >= 1e6
        ? `${(info.signed_notional / 1e6).toFixed(0)}M`
        : `${info.signed_notional.toFixed(0)}`;
  const sign = info.signed_notional >= 0 ? "+$" : "−$";
  const display = `${sign}${fmtNotional.replace(/^-/, "")}`;

  const tone = {
    pinned: "border-tm-pos/40 bg-tm-pos/10 text-tm-pos",
    volatile: "border-tm-warn/40 bg-tm-warn/10 text-tm-warn",
    mixed: "border-tm-rule bg-tm-bg-2 text-tm-muted",
  }[info.regime];

  const label = {
    zh: { pinned: "钉住", volatile: "趋势", mixed: "中性" },
    en: { pinned: "PINNED", volatile: "VOLATILE", mixed: "MIXED" },
  }[locale][info.regime];

  const tip =
    locale === "zh"
      ? `GEX 衡量做市商净 gamma 暴露。钉住=做市商净多头 gamma 倾向于反向交易(买跌卖涨),volatile=做市商净空头 gamma 倾向于追涨杀跌。\n当前 signed_notional=${display},n_strikes=${info.n_strikes},dominant_expiry=${info.dominant_expiry}。ALPHA_GEX_REGIME_BAND_USD 调整阈值。`
      : `GEX measures dealer net-gamma exposure. PINNED = dealers net-long gamma, reversion-friendly (buy dip / sell rip). VOLATILE = dealers net-short gamma, trend continuation. signed_notional=${display}, n_strikes=${info.n_strikes}, dominant_expiry=${info.dominant_expiry}. Tune via ALPHA_GEX_REGIME_BAND_USD.`;

  return (
    <div
      title={tip}
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-tm-mono text-[10px] ${tone}`}
    >
      <span className="opacity-70">GEX</span>
      <span className="font-semibold">{label}</span>
      <span className="opacity-60">{display}</span>
    </div>
  );
}
