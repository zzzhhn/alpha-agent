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
} from "@/lib/api/factor-lab";
import { TmPane, TmScreen } from "@/components/tm/TmPane";
import { AdminAccessNote } from "@/components/layout/SystemHealth";
import EvolutionObservatory from "@/components/evolution/EvolutionObservatory";
import { ChangeHistoryTable } from "@/components/evolution/ChangeHistoryTable";
import { ProposalsTable } from "@/components/evolution/ProposalsTable";
import { pendingReviewCounts } from "@/components/evolution/review-state";
import { EvolutionUnavailable } from "@/components/evolution/EvolutionUnavailable";
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
  failures: string[];
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

  const namedResults = [
    ["IC trend", icTrend],
    ["IC annotations", icAnnotations],
    ["weights", weights],
    ["calibration", calibration],
    ["change ledger", changes],
    ["proposals", proposals],
  ] as const;

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
    failures: namedResults.filter(([, result]) => result.status === "rejected").map(([name]) => name),
  };
}

// Proposals trio data, merged from the former /factor-lab page (kept as its own
// fetch so this page's existing fetchProposals — which feeds the health strip —
// is untouched). Mirrors the old factor-lab page's fetch exactly (revalidate:0).
async function fetchFactorLab() {
  const [diagSettled, pendingSettled, allSettled, lessonsSettled, briefingSettled] =
    await Promise.allSettled([
      fetchFactorDiagnostic({ revalidate: 0, tags: ["factor-lab-diagnostic"] }),
      fetchFactorProposals("pending", { revalidate: 0, tags: ["factor-lab-pending"] }, "expression"),
      fetchFactorProposals(undefined, { revalidate: 0, tags: ["factor-lab-history"] }),
      fetchMiningLessons(20, { revalidate: 0, tags: ["factor-lab-lessons"] }),
      fetchBriefing({ revalidate: 0, tags: ["factor-lab-briefing"] }),
    ]);
  const diagnostic = diagSettled.status === "fulfilled" ? diagSettled.value : null;
  const pending =
    pendingSettled.status === "fulfilled" ? pendingSettled.value.proposals.filter((p) => p.status === "pending") : null;
  const pendingGroups =
    pendingSettled.status === "fulfilled" ? pendingSettled.value.groups ?? null : null;
  const all = allSettled.status === "fulfilled" ? allSettled.value.proposals : null;
  const lessons =
    lessonsSettled.status === "fulfilled" ? lessonsSettled.value.lessons : null;
  const briefing =
    briefingSettled.status === "fulfilled"
      ? briefingSettled.value
      : null;
  return {
    diagnostic,
    pending,
    pendingGroups,
    history: all?.filter((p) => p.status !== "pending") ?? null,
    lessons,
    briefing,
  };
}

export default async function EvolutionPage() {
  const locale = await getServerLocale();
  const [
    { icTrend, icAnnotations, weights, calibration, changes, proposals, failures },
    { diagnostic, pending, pendingGroups, history, lessons, briefing },
  ] = await Promise.all([fetchAllEvolution(), fetchFactorLab()]);
  const liveExpression = diagnostic?.current_expression ?? "";

  // Decision-first header (P0): synthesize the always-present evidence into a
  // one-glance "is the self-evolution effective & trustworthy?" read.
  const health = assessEvolutionHealth({ icTrend, calibration, weights, proposals });

  const zh = locale === "zh";
  const policyPending = proposals?.proposals.filter((proposal) => proposal.status === "pending") ?? null;
  // Review counts are per distinct expression: 117 rows were 15 expressions.
  const review = pendingReviewCounts(policyPending, pendingGroups ? pendingGroups.map(() => ({ status: "pending" })) : pending);

  return (
    <TmScreen>
      <AdminAccessNote />
      <EvolutionObservatory
        locale={locale}
        health={health}
        icTrend={icTrend}
        annotations={icAnnotations}
        weights={weights?.weights ?? []}
        calibration={calibration}
        changes={changes?.changes ?? []}
        review={review}
        failures={failures}
      >
        <div id="evolution-review" tabIndex={-1} aria-label={zh ? "审查变化" : "Review changes"} className="grid scroll-mt-3 grid-cols-1 items-start gap-4 border-b border-tm-rule px-4 py-4 lg:px-6 xl:grid-cols-2">
          <div className="min-w-0 space-y-3">
            <PendingProposalsSection proposals={pending} groups={pendingGroups} liveExpression={liveExpression} />
            <TmPane title={zh ? "策略参数待审" : "Policy proposals"} meta={review.policy?.toString()}>
              {policyPending === null ? <EvolutionUnavailable locale={locale} /> : <ProposalsTable proposals={policyPending} locale={locale} />}
            </TmPane>
          </div>
          <div className="min-w-0 space-y-3">
            <TmPane title={zh ? "变更账本" : "Change ledger"} meta={changes?.changes.length.toString()}>
              {changes === null ? <EvolutionUnavailable locale={locale} /> : <ChangeHistoryTable changes={changes.changes} locale={locale} />}
            </TmPane>
            {history === null ? (
              <TmPane title={zh ? "方法论提案历史" : "Methodology proposal history"}><EvolutionUnavailable locale={locale} /></TmPane>
            ) : <HistoryCollapsedSection history={history} />}
          </div>
        </div>
      </EvolutionObservatory>

      <details className="border-b border-tm-rule px-4 py-3 lg:px-6">
        <summary className="cursor-pointer font-tm-mono text-xs text-tm-muted hover:text-tm-fg">
          {zh ? "方法论诊断、挖掘简报与学习日志" : "Methodology diagnostics, briefing and journal"}
        </summary>
        <div className="mt-3 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
          <FactorLabDecisionCard locale={locale} diagnostic={diagnostic} />
          {briefing === null ? <TmPane title={zh ? "挖掘简报" : "Mining briefing"}><EvolutionUnavailable locale={locale} /></TmPane> : <BriefingPane briefing={briefing} locale={locale} />}
          {lessons === null ? <TmPane title={zh ? "学习日志" : "Learning journal"}><EvolutionUnavailable locale={locale} /></TmPane> : <MiningJournalPane lessons={lessons} locale={locale} />}
        </div>
      </details>
    </TmScreen>
  );
}
