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
import { t } from "@/lib/i18n";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { IcTrendChart } from "@/components/evolution/IcTrendChart";
import { ReliabilityChart } from "@/components/evolution/ReliabilityChart";
import { WeightDeltaTable } from "@/components/evolution/WeightDeltaTable";
import { ChangeHistoryTable } from "@/components/evolution/ChangeHistoryTable";
import { ProposalsTable } from "@/components/evolution/ProposalsTable";
import EvolutionHealthStrip from "@/components/evolution/EvolutionHealthStrip";
import { assessEvolutionHealth } from "@/lib/evolution-health";

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
      fetchIcTrend(30, { revalidate: 60, tags: ["evolution-ic-trend"] }),
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

export default async function EvolutionPage() {
  const locale = await getServerLocale();
  const { icTrend, icAnnotations, weights, calibration, changes, proposals } =
    await fetchAllEvolution();

  // Decision-first header (P0): synthesize the always-present evidence into a
  // one-glance "is the self-evolution effective & trustworthy?" read.
  const health = assessEvolutionHealth({ icTrend, calibration, weights, proposals });

  const tr = (key: string) => t(locale, key as Parameters<typeof t>[1]);
  const fill = (key: string, vars: Record<string, string | number>) => {
    let s = tr(key);
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
    return s;
  };
  const unavailable = tr("evolution.unavailable");
  const loadFailed = tr("evolution.load_failed");

  return (
    <TmScreen>
      <EvolutionHealthStrip health={health} locale={locale} />

      {/* ── Section 1: Signal IC Trend ──────────────────────────────── */}
      <TmPane
        title={tr("evolution.pane.ic_trend")}
        meta={
          icTrend
            ? fill("evolution.ic.meta", {
                n: icTrend.series.length,
                d: icTrend.window_days,
              })
            : unavailable
        }
      >
        {icTrend ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {fill("evolution.ic.sub", {
                n: icTrend.series.length,
                d: icTrend.window_days,
              })}
            </p>
            <IcTrendChart
              series={icTrend.series}
              locale={locale}
              annotations={icAnnotations}
            />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {loadFailed}
          </p>
        )}
      </TmPane>

      {/* ── Section 2: Confidence Calibration ──────────────────────── */}
      <TmPane
        title={tr("evolution.pane.calibration")}
        meta={
          calibration
            ? calibration.applied
              ? fill("evolution.cal.meta_applied", { n: calibration.n_pairs })
              : fill("evolution.cal.meta_accumulating", { n: calibration.n_pairs })
            : unavailable
        }
      >
        {calibration ? (
          <div className="px-3 py-2.5">
            {calibration.applied ? (
              <p className="font-tm-mono text-[11px] text-tm-fg-2">
                {fill("evolution.cal.sub_applied", {
                  n: calibration.n_pairs,
                  b: calibration.buckets.length,
                })}
                {calibration.as_of ? ` · ${calibration.as_of}` : ""}
              </p>
            ) : (
              <p className="font-tm-mono text-[11px] text-tm-warn">
                {fill("evolution.cal.sub_accumulating", { n: calibration.n_pairs })}
              </p>
            )}
            <ReliabilityChart calibration={calibration} locale={locale} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {loadFailed}
          </p>
        )}
      </TmPane>

      {/* ── Section 3: Adaptive Weights ────────────────────────────── */}
      <TmPane
        title={tr("evolution.pane.weights")}
        meta={
          weights
            ? fill("evolution.weights.meta", { n: weights.weights.length })
            : unavailable
        }
      >
        {weights ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {fill("evolution.weights.sub", { n: weights.weights.length })}
            </p>
            <WeightDeltaTable weights={weights.weights} locale={locale} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {loadFailed}
          </p>
        )}
      </TmPane>

      {/* ── Section 4: Change History ───────────────────────────────── */}
      <TmPane
        title={tr("evolution.pane.changes")}
        meta={
          changes
            ? fill("evolution.changes.meta", { n: changes.changes.length })
            : unavailable
        }
      >
        {changes ? (
          <div className="px-3 py-2.5">
            <p className="font-tm-mono text-[11px] text-tm-fg-2">
              {fill("evolution.changes.sub", { n: changes.changes.length })}
            </p>
            <ChangeHistoryTable changes={changes.changes} locale={locale} />
          </div>
        ) : (
          <p className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-neg">
            {loadFailed}
          </p>
        )}
      </TmPane>

      {/* ── Section 5: Methodology Proposals ──────────────────────── */}
      <TmPane
        title={tr("evolution.pane.proposals")}
        meta={
          proposals
            ? fill("evolution.proposals.meta", { n: proposals.proposals.length })
            : unavailable
        }
      >
        <div className="px-3 py-2.5">
          {proposals ? (
            <ProposalsTable proposals={proposals.proposals} locale={locale} />
          ) : (
            <p className="font-tm-mono text-[11px] text-tm-neg">{loadFailed}</p>
          )}
        </div>
      </TmPane>
    </TmScreen>
  );
}
