import {
  fetchIcTrend,
  fetchEvolutionWeights,
  fetchEvolutionCalibration,
  fetchEvolutionChanges,
  fetchProposals,
  type IcTrendResponse,
  type EvolutionWeightsResponse,
  type EvolutionCalibration,
  type EvolutionChangesResponse,
  type ProposalsResponse,
} from "@/lib/api/evolution";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { IcTrendChart } from "@/components/evolution/IcTrendChart";
import { ReliabilityChart } from "@/components/evolution/ReliabilityChart";
import { WeightDeltaTable } from "@/components/evolution/WeightDeltaTable";
import { ChangeHistoryTable } from "@/components/evolution/ChangeHistoryTable";
import { ProposalsTable } from "@/components/evolution/ProposalsTable";

// Server component — fetches all evolution endpoints in parallel and renders
// section containers. ProposalsTable (Phase 2b) replaces the old placeholder.

async function fetchAllEvolution(): Promise<{
  icTrend: IcTrendResponse | null;
  weights: EvolutionWeightsResponse | null;
  calibration: EvolutionCalibration | null;
  changes: EvolutionChangesResponse | null;
  proposals: ProposalsResponse | null;
}> {
  const [icTrend, weights, calibration, changes, proposals] =
    await Promise.allSettled([
      fetchIcTrend(30, { revalidate: 60, tags: ["evolution-ic-trend"] }),
      fetchEvolutionWeights({ revalidate: 60, tags: ["evolution-weights"] }),
      fetchEvolutionCalibration({
        revalidate: 60,
        tags: ["evolution-calibration"],
      }),
      fetchEvolutionChanges(50, { revalidate: 60, tags: ["evolution-changes"] }),
      fetchProposals({ revalidate: 0, tags: ["evolution-proposals"] }),
    ]);

  return {
    icTrend: icTrend.status === "fulfilled" ? icTrend.value : null,
    weights: weights.status === "fulfilled" ? weights.value : null,
    calibration:
      calibration.status === "fulfilled" ? calibration.value : null,
    changes: changes.status === "fulfilled" ? changes.value : null,
    proposals: proposals.status === "fulfilled" ? proposals.value : null,
  };
}

export default async function EvolutionPage() {
  const { icTrend, weights, calibration, changes, proposals } =
    await fetchAllEvolution();

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
            <WeightDeltaTable weights={weights.weights} />
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
            <ChangeHistoryTable changes={changes.changes} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            Failed to load change history.
          </p>
        )}
      </TmPane>

      {/* ── Section 5: Methodology Proposals ──────────────────────── */}
      <TmPane
        title="METHODOLOGY PROPOSALS"
        meta={
          proposals
            ? `${proposals.proposals.length} proposal${proposals.proposals.length !== 1 ? "s" : ""}`
            : "unavailable"
        }
      >
        <div className="px-3 py-2.5">
          {proposals ? (
            <ProposalsTable proposals={proposals.proposals} />
          ) : (
            <p className="font-tm-mono text-[11px] text-tm-neg">
              Failed to load proposals.
            </p>
          )}
        </div>
      </TmPane>
    </TmScreen>
  );
}
