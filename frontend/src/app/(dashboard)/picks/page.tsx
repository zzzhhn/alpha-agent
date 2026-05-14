import { fetchPicks } from "@/lib/api/picks";
import PicksBrowser from "@/components/picks/PicksBrowser";
import { TmScreen } from "@/components/tm/TmPane";

export const dynamic = "force-dynamic";

export default async function PicksPage() {
  // Server-render the default top-50 board; PicksBrowser (client) layers
  // debounced ticker search on top and re-queries /api/picks/lean.
  const initialData = await fetchPicks(50);

  return (
    <TmScreen>
      <PicksBrowser initialData={initialData} />
    </TmScreen>
  );
}
