import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmSubbar, TmSubbarKV, TmSubbarSep } from "@/components/tm/TmSubbar";

// Route-level Suspense fallback for /alpha. The real page renders:
//   TmSubbar (universe / direction / status pills / run button) ->
//   HYPOTHESIS.INPUT pane (textarea + universe select) ->
//   FACTOR.EXAMPLES pane (grid of ~10 cards with expression + metrics).
// Skeleton mirrors those 3 always-visible sections so the layout shift
// on hydration is minimal.
export default function AlphaLoading() {
  return (
    <TmScreen>
      <TmSubbar>
        <TmSubbarKV label="ALPHA" value="—" />
        <TmSubbarSep />
        <TmSubbarKV label="UNIVERSE" value="—" />
        <TmSubbarSep />
        <TmSubbarKV label="DIRECTION" value="—" />
      </TmSubbar>

      {/* HYPOTHESIS.INPUT — textarea (h-16) + row of select + tips text */}
      <TmPane title="HYPOTHESIS.INPUT" meta="— CHARS">
        <div className="flex flex-col gap-3 px-3 py-3">
          <div className="h-16 w-full animate-pulse rounded bg-tm-bg-2" />
          <div className="flex items-end gap-3">
            <div className="h-8 w-40 animate-pulse rounded bg-tm-bg-2" />
            <div className="ml-auto h-6 w-64 animate-pulse rounded bg-tm-bg-2" />
          </div>
        </div>
      </TmPane>

      {/* FACTOR.EXAMPLES — subtitle bar + 2-col grid of 6 example cards */}
      <TmPane title="FACTOR.EXAMPLES" meta="loading...">
        <div className="h-8 w-full animate-pulse rounded-none bg-tm-bg-2" />
        <div className="grid grid-cols-1 gap-px bg-tm-rule lg:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col gap-2 bg-tm-bg p-3"
              style={{ opacity: 1 - i * 0.08 }}
            >
              {/* name + badge row */}
              <div className="flex items-start justify-between gap-2">
                <div className="h-4 w-32 animate-pulse rounded bg-tm-bg-2" />
                <div className="h-4 w-16 animate-pulse rounded bg-tm-bg-2" />
              </div>
              {/* hypothesis text */}
              <div className="h-8 w-full animate-pulse rounded bg-tm-bg-2" />
              {/* expression code block */}
              <div className="h-6 w-full animate-pulse rounded bg-tm-bg-2" />
              {/* intuition lines */}
              <div className="h-10 w-full animate-pulse rounded bg-tm-bg-2" />
              {/* metrics + button row */}
              <div className="flex items-center justify-between border-t border-tm-rule pt-2">
                <div className="h-4 w-28 animate-pulse rounded bg-tm-bg-2" />
                <div className="h-6 w-14 animate-pulse rounded bg-tm-bg-2" />
              </div>
            </div>
          ))}
        </div>
      </TmPane>
    </TmScreen>
  );
}
