// Route-level Suspense fallback for /stock/[ticker]. Mirrors
// StockCardLayout's 3-column sidebar + 9-column main split so the
// page does not visually shift when the RSC fetch resolves.
export default function StockLoading() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 px-4 py-6">
      <aside className="lg:col-span-3 lg:sticky lg:top-4 self-start space-y-4">
        <div className="h-4 w-24 animate-pulse rounded bg-tm-bg-2" />
        <div className="h-8 w-20 animate-pulse rounded bg-tm-bg-2" />
        <div className="h-14 w-full animate-pulse rounded bg-tm-bg-2" />
        <div className="h-32 w-full animate-pulse rounded bg-tm-bg-2" />
        <div className="space-y-1">
          <div className="h-3 w-32 animate-pulse rounded bg-tm-bg-2" />
          <div className="h-3 w-24 animate-pulse rounded bg-tm-bg-2" />
        </div>
      </aside>
      <main className="lg:col-span-9 space-y-8 min-w-0">
        <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-3">
          <div className="h-5 w-40 animate-pulse rounded bg-tm-bg-3" />
          <div className="h-4 w-full animate-pulse rounded bg-tm-bg-3" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-tm-bg-3" />
        </section>
        <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-3">
          <div className="h-5 w-32 animate-pulse rounded bg-tm-bg-3" />
          <div className="h-24 w-full animate-pulse rounded bg-tm-bg-3" />
        </section>
        <section>
          <div className="h-5 w-44 mb-3 animate-pulse rounded bg-tm-bg-2" />
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <div className="md:col-span-4 h-48 animate-pulse rounded bg-tm-bg-2" />
            <div className="md:col-span-8 h-48 animate-pulse rounded bg-tm-bg-2" />
          </div>
        </section>
        <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
          <div className="h-5 w-32 mb-3 animate-pulse rounded bg-tm-bg-3" />
          <div className="h-80 w-full animate-pulse rounded bg-tm-bg-3" />
        </section>
      </main>
    </div>
  );
}
