// frontend/src/app/(dashboard)/stock/[ticker]/page.tsx
import { fetchStock } from "@/lib/api/picks";
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
    if (e instanceof Error && e.message.includes("No rating")) notFound();
    throw e;
  }
}
