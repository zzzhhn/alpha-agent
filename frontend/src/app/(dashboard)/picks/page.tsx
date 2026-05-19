import { fetchPicks } from "@/lib/api/picks";
import PicksBrowser from "@/components/picks/PicksBrowser";
import { TmScreen } from "@/components/tm/TmPane";

// Page is dynamic by virtue of its server fetch, so we don't need the
// force-dynamic directive. Removing it lets the fetch below benefit from
// the Next.js Data Cache, so a repeat visit within 60s reuses the cached
// response instead of round-tripping FastAPI. RefreshButton stays the
// authoritative trigger for fresher data via the backend POST.
export default async function PicksPage() {
  // Server-render the default top-50 board; PicksBrowser (client) layers
  // debounced ticker search on top and re-queries /api/picks/lean.
  const initialData = await fetchPicks(50, undefined, undefined, {
    revalidate: 60,
    tags: ["picks-lean"],
  });

  return (
    <TmScreen>
      <PicksBrowser initialData={initialData} />
    </TmScreen>
  );
}
