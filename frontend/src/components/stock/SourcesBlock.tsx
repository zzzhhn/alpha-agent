import type { RatingCard } from "@/lib/api/picks";

export default function SourcesBlock({ card }: { card: RatingCard }) {
  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-2 text-tm-fg">Sources &amp; Timestamps</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-tm-fg-2 border-b border-tm-rule">
            <th className="text-left px-2 py-1">signal</th>
            <th className="text-left px-2 py-1">source</th>
            <th className="text-left px-2 py-1">timestamp</th>
          </tr>
        </thead>
        <tbody>
          {card.breakdown.map((b) => (
            <tr key={b.signal} className="border-b border-tm-rule">
              <td className="px-2 py-1 text-tm-fg">{b.signal}</td>
              <td className="px-2 py-1 text-tm-muted">{b.source}</td>
              <td className="px-2 py-1 text-tm-muted">
                {new Date(b.timestamp).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
