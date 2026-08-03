import { getServerLocale } from "@/lib/server-locale";
import {
  fetchIcTrend,
  fetchIcAnnotations,
  fetchEvolutionWeights,
  fetchEvolutionCalibration,
  fetchEvolutionChanges,
  fetchProposals,
  type IcTrendResponse,
  type IcAnnotation,
  type EvolutionWeightsResponse,
  type EvolutionCalibration,
  type EvolutionChangesResponse,
  type ProposalsResponse,
} from "@/lib/api/evolution";
import {
  fetchFactorDiagnostic,
  fetchFactorProposals,
  fetchMiningLessons,
  fetchBriefing,
  type MiningBriefing,
} from "@/lib/api/factor-lab";
import { TmScreen } from "@/components/tm/TmPane";
import EvolutionHealthStrip from "@/components/evolution/EvolutionHealthStrip";
import EvolutionObservatory from "@/components/evolution/EvolutionObservatory";
import { assessEvolutionHealth } from "@/lib/evolution-health";
// Methodology-proposals UI, merged in from the former /factor-lab page (the two
// nav slots both surfaced proposals; consolidated into this one monitor).
import { FactorLabDecisionCard } from "@/components/factor-lab/FactorLabDecisionCard";
import { PendingProposalsSection } from "@/components/factor-lab/PendingProposalsSection";
import { HistoryCollapsedSection } from "@/components/factor-lab/HistoryCollapsedSection";
import { MiningJournalPane } from "@/components/factor-lab/MiningJournalPane";
import { BriefingPane } from "@/components/factor-lab/BriefingPane";

// Server component — fetches all evolution endpoints in parallel and renders
// section containers. SSR-correct locale comes from the shared cookie reader.
async function fetchAllEvolution(): Promise<{
  icTrend: IcTrendResponse | null;
  icAnnotations: IcAnnotation[];
  weights: EvolutionWeightsResponse | null;
  calibration: EvolutionCalibration | null;
  changes: EvolutionChangesResponse | null;
  proposals: ProposalsResponse | null;
}> {
  const [icTrend, icAnnotations, weights, calibration, changes, proposals] =
    await Promise.allSettled([
      fetchIcTrend(30, 5, { revalidate: 60, tags: ["evolution-ic-trend"] }),
      fetchIcAnnotations(30, { revalidate: 60, tags: ["evolution-ic-annotations"] }),
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
    icAnnotations:
      icAnnotations.status === "fulfilled"
        ? icAnnotations.value.annotations
        : [],
    weights: weights.status === "fulfilled" ? weights.value : null,
    calibration:
      calibration.status === "fulfilled" ? calibration.value : null,
    changes: changes.status === "fulfilled" ? changes.value : null,
    proposals: proposals.status === "fulfilled" ? proposals.value : null,
  };
}

// Proposals trio data, merged from the former /factor-lab page (kept as its own
// fetch so this page's existing fetchProposals — which feeds the health strip —
// is untouched). Mirrors the old factor-lab page's fetch exactly (revalidate:0).
async function fetchFactorLab() {
  const [diagSettled, pendingSettled, allSettled, lessonsSettled, briefingSettled] =
    await Promise.allSettled([
      fetchFactorDiagnostic({ revalidate: 0, tags: ["factor-lab-diagnostic"] }),
      fetchFactorProposals("pending", { revalidate: 0, tags: ["factor-lab-pending"] }),
      fetchFactorProposals(undefined, { revalidate: 0, tags: ["factor-lab-history"] }),
      fetchMiningLessons(20, { revalidate: 0, tags: ["factor-lab-lessons"] }),
      fetchBriefing({ revalidate: 0, tags: ["factor-lab-briefing"] }),
    ]);
  const diagnostic = diagSettled.status === "fulfilled" ? diagSettled.value : null;
  const pending =
    pendingSettled.status === "fulfilled" ? pendingSettled.value.proposals : [];
  const all = allSettled.status === "fulfilled" ? allSettled.value.proposals : [];
  const lessons =
    lessonsSettled.status === "fulfilled" ? lessonsSettled.value.lessons : [];
  const briefing: MiningBriefing =
    briefingSettled.status === "fulfilled"
      ? briefingSettled.value
      : { validated: [], flagged: [], failure_insights: [] };
  return {
    diagnostic,
    pending,
    history: all.filter((p) => p.status !== "pending"),
    lessons,
    briefing,
  };
}

export default async function EvolutionPage() {
  const locale = await getServerLocale();
  const [
    { icTrend, icAnnotations, weights, calibration, changes, proposals },
    { diagnostic, pending, history, lessons, briefing },
  ] = await Promise.all([fetchAllEvolution(), fetchFactorLab()]);
  const liveExpression = diagnostic?.current_expression ?? "";

  // Decision-first header (P0): synthesize the always-present evidence into a
  // one-glance "is the self-evolution effective & trustworthy?" read.
  const health = assessEvolutionHealth({ icTrend, calibration, weights, proposals });

  const pendingCount = proposals?.proposals.filter((proposal) => proposal.status === "pending").length ?? 0;

  return (
    <TmScreen>
      <EvolutionHealthStrip health={health} locale={locale} />
      <EvolutionObservatory
        locale={locale}
        icTrend={icTrend}
        annotations={icAnnotations}
        weights={weights?.weights ?? []}
        calibration={calibration}
        changes={changes?.changes ?? []}
        pendingCount={pendingCount}
      />

      {/* ── Section 5: Methodology Proposals (merged from /factor-lab) ──
          The decision card + actionable pending list + collapsed history,
          richer than the prior read-only table. `proposals` (fetchProposals)
          still feeds the health strip above. */}
      <div id="evolution-review">
        <FactorLabDecisionCard locale={locale} diagnostic={diagnostic} />
      </div>

      {/* Phase D: compressed 3-bucket briefing — the miner's output squeezed to
          validated / flagged / repeated-failure directions. Sits right under the
          decision card so the headline read is above the raw pending list. */}
      <BriefingPane briefing={briefing} locale={locale} />

      <PendingProposalsSection proposals={pending} liveExpression={liveExpression} />

      {/* ── Section 6: Mining Journal (Phase A memory + Phase B rejects) ──
          What the self-evolving miner has learned: one KEEP/WEAK/AVOID lesson
          per evaluated candidate. The proposer reads these back each round. */}
      <MiningJournalPane lessons={lessons} locale={locale} />

      <HistoryCollapsedSection history={history} />
    </TmScreen>
  );
}
