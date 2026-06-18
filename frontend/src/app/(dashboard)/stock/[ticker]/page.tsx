// frontend/src/app/(dashboard)/stock/[ticker]/page.tsx
import {
  fetchStock,
  fetchOhlcv,
  fetchChartEvents,
  type OhlcvBar,
  type ChartEvent,
} from "@/lib/api/picks";
import { fetchSignalHealth, type SignalHealthEntry } from "@/lib/api/signal_health";
import { ApiException } from "@/lib/api/client";
import StockCardLayout from "@/components/stock/StockCardLayout";
import { notFound } from "next/navigation";

// Page is dynamic by data dependency (the await below); the force-dynamic
// directive was an over-precaution that defeated Next.js Data Cache. With
// it gone, the per-ticker fetches were cached for 60s + tagged. BUT the
// revalidateTag path those tags relied on was never built (no revalidate
// route, no cron call), so card + chart served stale-while-revalidate: a
// ticker not revisited for days showed last-cached (2-week-old) data on first
// open. Card + OHLCV now fetch no-store (fresh per open); events keep a short
// cache since their cache key already rotates daily (from/today in the URL).

export default async function StockPage({
  params,
}: {
  params: { ticker: string };
}) {
  try {
    const ticker = params.ticker.toUpperCase();
    // Six-month event window for the price chart. Computed once server-
    // side so the RSC fetch is deterministic and Next Data Cache can key
    // off these exact strings across visits.
    const today = new Date().toISOString().slice(0, 10);
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    const from = sixMonthsAgo.toISOString().slice(0, 10);

    // Four parallel fetches — biggest single waterfall remaining in
    // Phase B was PriceChart's client-side OHLCV + events round-trip.
    // Pulling them up here lets all four share the RSC's wall-clock
    // window and ship in the initial HTML payload; the chart paints
    // on first hydration tick instead of after a second roundtrip.
    const [
      { card, stale },
      healthResult,
      ohlcvResult,
      eventsResult,
    ] = await Promise.all([
      // no-store: detail card must reflect the current rating/price, not a
      // stale-while-revalidate snapshot from a prior visit (the revalidateTag
      // path the old revalidate:60 relied on was never built).
      fetchStock(ticker),
      fetchSignalHealth({ revalidate: 3600, tags: ["signal-health"] }).catch(
        () => ({ signals: [] as SignalHealthEntry[] }),
      ),
      // no-store: the price chart must show current daily bars. The backend
      // OHLCV endpoint is a live, fresh yfinance read; the prior revalidate:60
      // cache (with a tag nothing ever revalidated) served 2-week-old candles
      // on the first visit to a ticker not opened recently.
      fetchOhlcv(ticker, "6mo").catch(() => ({
        ticker,
        period: "6mo",
        bars: [] as OhlcvBar[],
      })),
      fetchChartEvents(ticker, from, today, {
        revalidate: 300,
        tags: [`events-${ticker}`],
      }).catch(() => ({
        ticker,
        from_ts: from,
        to_ts: today,
        events: [] as ChartEvent[],
      })),
    ]);
    const healthMap: Record<string, SignalHealthEntry> = {};
    for (const s of healthResult.signals) healthMap[s.name] = s;
    return (
      <StockCardLayout
        card={card}
        stale={stale}
        healthMap={healthMap}
        bars={ohlcvResult.bars}
        chartEvents={eventsResult.events}
      />
    );
  } catch (e) {
    // A 404 means the ticker is in neither signals table, so render the
    // not-found page. The old check keyed off e.message.includes("No
    // rating"), but ApiException.message comes from the response body's
    // `message` field while FastAPI returns `detail`, so it was always
    // undefined and every 404 fell through to a raw server exception.
    if (e instanceof ApiException && e.status === 404) notFound();
    throw e;
  }
}
