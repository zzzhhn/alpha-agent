import { fetchPicks, type FactorMode, type PicksSide } from "@/lib/api/picks";
import PicksBrowser from "@/components/picks/PicksBrowser";
import { RECOMMENDATION_BOARD_SIZE } from "@/components/picks/paper-order-source";
import OnboardingBanner from "@/components/layout/OnboardingBanner";
import { TmScreen } from "@/components/tm/TmPane";

// Page is dynamic by virtue of its server fetch, so we don't need the
// force-dynamic directive. Removing it lets the fetch below benefit from
// the Next.js Data Cache, so a repeat visit within 60s reuses the cached
// response instead of round-tripping FastAPI. RefreshButton stays the
// authoritative trigger for fresher data via the backend POST.
export default async function PicksPage({ searchParams }: {
  searchParams: Promise<{ mode?: string | string[]; side?: string | string[] }>;
}) {
  const params = await searchParams;
  const mode: FactorMode | undefined = params.mode === "long" || params.mode === "short" ? params.mode : undefined;
  const side: PicksSide = params.side === "short" ? "short" : "long";
  const initialData = await fetchPicks(RECOMMENDATION_BOARD_SIZE, undefined, mode, side, {
    revalidate: 60,
    tags: ["picks-lean"],
  });

  return (
    <TmScreen className="[&>*]:shrink-0">
      <OnboardingBanner />
      <PicksBrowser key={`${mode ?? "default"}:${side}`} initialData={initialData} initialMode={mode} initialSide={side} />
    </TmScreen>
  );
}
