export default function PriceChart({ ticker }: { ticker: string }) {
  return (
    <section className="rounded border border-zinc-800 p-4">
      <h2 className="text-lg font-semibold mb-2">Price / Technicals</h2>
      <div className="h-64 flex items-center justify-center text-zinc-600 text-sm">
        Chart for {ticker} — full lightweight-charts integration in M4
      </div>
    </section>
  );
}
