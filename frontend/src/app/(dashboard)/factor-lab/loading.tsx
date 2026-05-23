import { TmScreen, TmPane } from "@/components/tm/TmPane";

// Route-level Suspense fallback for /factor-lab. The real RSC page has
// 6 TmPane sections (lines 38-147 of page.tsx), in order:
//   1. FACTOR LAB — intro text (~h-12)
//   2. CURRENT LIVE EXPRESSION — <pre> code block (~h-20)
//   3. DIAGNOSTIC SNAPSHOT — 2-3 lines of KV text (~h-20)
//   4. PROPOSE NEW CANDIDATES — single button (~h-12)
//   5. PENDING PROPOSALS — proposals table (~h-32)
//   6. HISTORY — history table (~h-32)
export default function FactorLabLoading() {
  return (
    <TmScreen>
      {/* Section 1: intro header */}
      <TmPane title="FACTOR LAB">
        <div className="px-3 py-3">
          <div className="h-4 w-2/3 animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 2: CURRENT LIVE EXPRESSION — code pre block */}
      <TmPane title="CURRENT LIVE EXPRESSION" meta="—">
        <div className="px-3 py-3">
          <div className="h-20 w-full animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 3: DIAGNOSTIC SNAPSHOT — 3 KV text lines */}
      <TmPane title="DIAGNOSTIC SNAPSHOT" meta="—">
        <div className="flex flex-col gap-2 px-3 py-3">
          <div className="h-4 w-full animate-pulse rounded bg-tm-bg-2" />
          <div className="h-4 w-4/5 animate-pulse rounded bg-tm-bg-2" />
          <div className="h-4 w-3/5 animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 4: PROPOSE NEW CANDIDATES — single button */}
      <TmPane title="PROPOSE NEW CANDIDATES">
        <div className="px-3 py-3">
          <div className="h-8 w-40 animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 5: PENDING PROPOSALS — table rows */}
      <TmPane title="PENDING PROPOSALS" meta="— pending">
        <div className="px-3 py-3">
          <div className="flex flex-col gap-px">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-8 w-full animate-pulse rounded bg-tm-bg-2"
                style={{ opacity: 1 - i * 0.15 }}
              />
            ))}
          </div>
        </div>
      </TmPane>

      {/* Section 6: HISTORY — table rows */}
      <TmPane title="HISTORY" meta="— records">
        <div className="px-3 py-3">
          <div className="flex flex-col gap-px">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-7 w-full animate-pulse rounded bg-tm-bg-2"
                style={{ opacity: 1 - i * 0.1 }}
              />
            ))}
          </div>
        </div>
      </TmPane>
    </TmScreen>
  );
}
