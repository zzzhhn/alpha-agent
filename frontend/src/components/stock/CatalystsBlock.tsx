import type { RatingCard } from "@/lib/api/picks";

export default function CatalystsBlock({ card }: { card: RatingCard }) {
  const cal = card.breakdown.find((b) => b.signal === "calendar")?.raw;
  const earn = card.breakdown.find((b) => b.signal === "earnings")?.raw;
  const news = card.breakdown.find((b) => b.signal === "news")?.raw;
  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-2 text-tm-fg">Catalysts</h2>
      <div className="text-sm space-y-2 text-tm-fg">
        <div>
          <span className="text-tm-fg-2">Earnings:</span>{" "}
          <span className="font-mono text-tm-muted">{earn ? JSON.stringify(earn) : "—"}</span>
        </div>
        <div>
          <span className="text-tm-fg-2">Calendar:</span>{" "}
          <span className="font-mono text-tm-muted">{cal ? JSON.stringify(cal) : "—"}</span>
        </div>
        <div>
          <span className="text-tm-fg-2">News:</span>{" "}
          <span className="font-mono text-tm-muted">{news ? JSON.stringify(news) : "—"}</span>
        </div>
      </div>
    </section>
  );
}
