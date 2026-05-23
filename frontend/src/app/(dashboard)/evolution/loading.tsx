import { TmScreen, TmPane } from "@/components/tm/TmPane";

// Route-level Suspense fallback for /evolution. The real RSC page has
// 5 TmPane sections (lines 52-183 of page.tsx), in order:
//   1. SIGNAL IC TREND — text + IcTrendChart (~h-48 for chart)
//   2. CONFIDENCE CALIBRATION — text + ReliabilityChart (~h-48 for chart)
//   3. ADAPTIVE WEIGHTS — text + WeightDeltaTable (~h-40)
//   4. CHANGE HISTORY — text + ChangeHistoryTable (~h-40)
//   5. METHODOLOGY PROPOSALS — ProposalsTable (~h-40)
export default function EvolutionLoading() {
  return (
    <TmScreen>
      {/* Section 1: SIGNAL IC TREND — caption + chart area */}
      <TmPane title="SIGNAL IC TREND" meta="—">
        <div className="px-3 py-3">
          <div className="mb-2 h-4 w-48 animate-pulse rounded bg-tm-bg-2" />
          <div className="h-48 w-full animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 2: CONFIDENCE CALIBRATION — caption + chart area */}
      <TmPane title="CONFIDENCE CALIBRATION" meta="—">
        <div className="px-3 py-3">
          <div className="mb-2 h-4 w-56 animate-pulse rounded bg-tm-bg-2" />
          <div className="h-48 w-full animate-pulse rounded bg-tm-bg-2" />
        </div>
      </TmPane>

      {/* Section 3: ADAPTIVE WEIGHTS — caption + table rows */}
      <TmPane title="ADAPTIVE WEIGHTS" meta="—">
        <div className="px-3 py-3">
          <div className="mb-2 h-4 w-40 animate-pulse rounded bg-tm-bg-2" />
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

      {/* Section 4: CHANGE HISTORY — caption + table rows */}
      <TmPane title="CHANGE HISTORY" meta="—">
        <div className="px-3 py-3">
          <div className="mb-2 h-4 w-44 animate-pulse rounded bg-tm-bg-2" />
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

      {/* Section 5: METHODOLOGY PROPOSALS — table rows */}
      <TmPane title="METHODOLOGY PROPOSALS" meta="—">
        <div className="px-3 py-3">
          <div className="flex flex-col gap-px">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="h-8 w-full animate-pulse rounded bg-tm-bg-2"
                style={{ opacity: 1 - i * 0.12 }}
              />
            ))}
          </div>
        </div>
      </TmPane>
    </TmScreen>
  );
}
