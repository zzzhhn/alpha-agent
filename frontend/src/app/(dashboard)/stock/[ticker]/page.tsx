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
// it gone, the per-ticker fetch is cached for 60s + tagged so the cron can
// revalidate explicitly when ratings change.

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
      fetchStock(ticker, {
        revalidate: 60,
        tags: [`stock-${ticker}`],
      }),
      fetchSignalHealth({ revalidate: 3600, tags: ["signal-health"] }).catch(
        () => ({ signals: [] as SignalHealthEntry[] }),
      ),
      fetchOhlcv(ticker, "6mo", {
        revalidate: 60,
        tags: [`ohlcv-${ticker}`],
      }).catch(() => ({
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
