// frontend/src/app/(dashboard)/stock/[ticker]/page.tsx
import { fetchStock } from "@/lib/api/picks";
import { ApiException } from "@/lib/api/client";
import StockCardLayout from "@/components/stock/StockCardLayout";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function StockPage({
  params,
}: {
  params: { ticker: string };
}) {
  try {
    const { card, stale } = await fetchStock(params.ticker);
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
