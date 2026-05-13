export default function PriceChart({ ticker }: { ticker: string }) {
  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-2 text-tm-fg">Price / Technicals</h2>
      <div className="h-64 flex items-center justify-center text-tm-muted text-sm">
        Chart for {ticker} — full lightweight-charts integration in M4
      </div>
    </section>
  );
}
