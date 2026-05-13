import type { RatingCard } from "@/lib/api/picks";

export default function CatalystsBlock({ card }: { card: RatingCard }) {
  const cal = card.breakdown.find((b) => b.signal === "calendar")?.raw;
  const earn = card.breakdown.find((b) => b.signal === "earnings")?.raw;
  const news = card.breakdown.find((b) => b.signal === "news")?.raw;
  return (
    <section className="rounded border border-zinc-800 p-4">
      <h2 className="text-lg font-semibold mb-2">Catalysts</h2>
      <div className="text-sm space-y-2">
        <div>
          <span className="text-zinc-500">Earnings:</span>{" "}
          {earn ? JSON.stringify(earn) : "—"}
        </div>
        <div>
          <span className="text-zinc-500">Calendar:</span>{" "}
          {cal ? JSON.stringify(cal) : "—"}
        </div>
        <div>
          <span className="text-zinc-500">News:</span>{" "}
          {news ? JSON.stringify(news) : "—"}
        </div>
      </div>
    </section>
  );
}
