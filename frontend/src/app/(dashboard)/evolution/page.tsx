import {
  fetchIcTrend,
  fetchEvolutionWeights,
  fetchEvolutionCalibration,
  fetchEvolutionChanges,
  type IcTrendResponse,
  type EvolutionWeightsResponse,
  type EvolutionCalibration,
  type EvolutionChangesResponse,
} from "@/lib/api/evolution";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { IcTrendChart } from "@/components/evolution/IcTrendChart";
import { ReliabilityChart } from "@/components/evolution/ReliabilityChart";

// Server component — fetches all four evolution endpoints in parallel and
// renders placeholder section containers. Task 5/6 will replace the
// placeholder divs with real charts and tables.

async function fetchAllEvolution(): Promise<{
  icTrend: IcTrendResponse | null;
  weights: EvolutionWeightsResponse | null;
  calibration: EvolutionCalibration | null;
  changes: EvolutionChangesResponse | null;
}> {
  const [icTrend, weights, calibration, changes] = await Promise.allSettled([
    fetchIcTrend(30, { revalidate: 60, tags: ["evolution-ic-trend"] }),
    fetchEvolutionWeights({ revalidate: 60, tags: ["evolution-weights"] }),
    fetchEvolutionCalibration({ revalidate: 60, tags: ["evolution-calibration"] }),
    fetchEvolutionChanges(50, { revalidate: 60, tags: ["evolution-changes"] }),
  ]);

  return {
    icTrend: icTrend.status === "fulfilled" ? icTrend.value : null,
    weights: weights.status === "fulfilled" ? weights.value : null,
    calibration: calibration.status === "fulfilled" ? calibration.value : null,
    changes: changes.status === "fulfilled" ? changes.value : null,
  };
}

export default async function EvolutionPage() {
  const { icTrend, weights, calibration, changes } = await fetchAllEvolution();

  return (
    <TmScreen>
      {/* ── Section 1: Signal IC Trend ──────────────────────────────── */}
      <TmPane
        title="SIGNAL IC TREND"
        meta={
          icTrend
            ? `${icTrend.series.length} signals · ${icTrend.window_days}d window`
            : "unavailable"
        }
      >
        {icTrend ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {icTrend.series.length} signal
              {icTrend.series.length !== 1 ? "s" : ""} · {icTrend.window_days}
              d rolling window
            </p>
            <IcTrendChart series={icTrend.series} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            Failed to load IC trend data.
          </p>
        )}
      </TmPane>

      {/* ── Section 2: Confidence Calibration ──────────────────────── */}
      <TmPane
        title="CONFIDENCE CALIBRATION"
        meta={
          calibration
            ? `${calibration.n_pairs} pairs · applied=${String(calibration.applied)}`
            : "unavailable"
        }
      >
        {calibration ? (
          <div className="px-3 py-2.5">
            {calibration.applied ? (
              <p className="font-tm-mono text-[11px] text-tm-fg-2">
                {calibration.n_pairs} calibration pairs ·{" "}
                {calibration.buckets.length} buckets · applied
                {calibration.as_of ? ` as of ${calibration.as_of}` : ""}
              </p>
            ) : (
              <p className="font-tm-mono text-[11px] text-tm-warn">
                Calibration accumulating ({calibration.n_pairs}/50 pairs)
              </p>
            )}
            <ReliabilityChart calibration={calibration} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            Failed to load calibration data.
          </p>
        )}
      </TmPane>

      {/* ── Section 3: Adaptive Weights ────────────────────────────── */}
      <TmPane
        title="ADAPTIVE WEIGHTS"
        meta={
          weights
            ? `${weights.weights.length} weight rows`
            : "unavailable"
        }
      >
        {weights ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {weights.weights.length} signal weight
              {weights.weights.length !== 1 ? "s" : ""}
            </p>
            {/* Task 6: WeightsTable */}
            <p className="mt-1 font-tm-mono text-[10.5px] text-tm-muted">
              Table placeholder — Task 6 replaces this with WeightsTable.
            </p>
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            Failed to load weights data.
          </p>
        )}
      </TmPane>

      {/* ── Section 4: Change History ───────────────────────────────── */}
      <TmPane
        title="CHANGE HISTORY"
        meta={
          changes
            ? `${changes.changes.length} changes`
            : "unavailable"
        }
      >
        {changes ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {changes.changes.length} change record
              {changes.changes.length !== 1 ? "s" : ""}
            </p>
            {/* Task 6: ChangesTable */}
            <p className="mt-1 font-tm-mono text-[10.5px] text-tm-muted">
              Table placeholder — Task 6 replaces this with ChangesTable.
            </p>
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            Failed to load change history.
          </p>
        )}
      </TmPane>

      {/* ── Section 5: Pending Methodology Proposals (disabled) ────── */}
      <TmPane
        title="METHODOLOGY PROPOSALS"
        meta="pending · Phase 2"
      >
        <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          Coming in Phase 2 (proposer + approval workflow). This section will
          list pending and approved methodology change proposals once the
          proposer and approval pipeline is implemented.
        </p>
      </TmPane>
    </TmScreen>
  );
}
