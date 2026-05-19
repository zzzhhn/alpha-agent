// frontend/src/app/(dashboard)/stock/[ticker]/page.tsx
import { fetchStock } from "@/lib/api/picks";
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
    const { card, stale } = await fetchStock(ticker, {
      revalidate: 60,
      tags: [`stock-${ticker}`],
    });
    return <StockCardLayout card={card} stale={stale} />;
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
