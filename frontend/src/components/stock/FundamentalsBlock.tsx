import type { RatingCard } from "@/lib/api/picks";

export default function FundamentalsBlock({ card }: { card: RatingCard }) {
  const fund = card.breakdown.find((b) => b.signal === "factor")?.raw;
  return (
    <section className="rounded border border-zinc-800 p-4">
      <h2 className="text-lg font-semibold mb-2">Fundamentals</h2>
      <pre className="text-xs text-zinc-400 overflow-x-auto">
        {fund
          ? JSON.stringify(fund, null, 2)
          : "Data limited (M3 placeholder; M4 wires real fundamentals)"}
      </pre>
    </section>
  );
}
