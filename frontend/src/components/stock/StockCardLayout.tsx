"use client";

import Link from "next/link";
import type { RatingCard } from "@/lib/api/picks";
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
