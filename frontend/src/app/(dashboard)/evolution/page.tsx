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
      <EvolutionObservatory
        locale={locale}
        health={health}
        icTrend={icTrend}
        annotations={icAnnotations}
        weights={weights?.weights ?? []}
        calibration={calibration}
        changes={changes?.changes ?? []}
        pendingCount={pendingCount}
      >
        {/* ── Decision ledger: proposals before on-demand telemetry detail ──
          The decision card + actionable pending list + collapsed history,
          richer than the prior read-only table. `proposals` (fetchProposals)
          still feeds the health strip above. */}
        <div id="evolution-review" className="grid grid-cols-[minmax(420px,0.85fr)_minmax(640px,1.15fr)] gap-4 border-b border-tm-rule px-6 py-4">
          <div className="min-w-0">
            <FactorLabDecisionCard locale={locale} diagnostic={diagnostic} />
          </div>
          <div className="min-w-0">
            <PendingProposalsSection proposals={pending} liveExpression={liveExpression} />
            <HistoryCollapsedSection history={history} />
          </div>
        </div>
      </EvolutionObservatory>

      <details className="border-b border-tm-rule px-6 py-3">
        <summary className="cursor-pointer font-tm-mono text-[11px] text-tm-muted hover:text-tm-fg">
          {locale === "zh" ? "展开挖掘简报与学习日志" : "Expand mining briefing and learning journal"}
        </summary>
        <div className="mt-3 grid grid-cols-2 gap-4">
          <BriefingPane briefing={briefing} locale={locale} />
          <MiningJournalPane lessons={lessons} locale={locale} />
        </div>
      </details>
    </TmScreen>
  );
}
