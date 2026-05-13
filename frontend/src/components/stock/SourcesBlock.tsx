import type { RatingCard } from "@/lib/api/picks";

export default function SourcesBlock({ card }: { card: RatingCard }) {
  return (
    <section className="rounded border border-zinc-800 p-4">
      <h2 className="text-lg font-semibold mb-2">Sources &amp; Timestamps</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-zinc-400 border-b border-zinc-800">
            <th className="text-left px-2 py-1">signal</th>
            <th className="text-left px-2 py-1">source</th>
            <th className="text-left px-2 py-1">timestamp</th>
          </tr>
        </thead>
        <tbody>
          {card.breakdown.map((b) => (
            <tr key={b.signal} className="border-b border-zinc-900">
              <td className="px-2 py-1">{b.signal}</td>
              <td className="px-2 py-1 text-zinc-500">{b.source}</td>
              <td className="px-2 py-1 text-zinc-500">
                {new Date(b.timestamp).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
