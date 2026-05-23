import {
  fetchFactorDiagnostic,
  fetchFactorProposals,
} from "@/lib/api/factor-lab";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { ProposeButton } from "@/components/factor-lab/ProposeButton";
import { PendingFactorProposalsTable } from "@/components/factor-lab/PendingFactorProposalsTable";
import { FactorHistoryTable } from "@/components/factor-lab/FactorHistoryTable";

// Force dynamic so that each request fetches fresh proposal state.
// This matches how /evolution handles proposals (revalidate: 0).
export const dynamic = "force-dynamic";

export default async function FactorLabPage() {
  const [diagSettled, pendingSettled, allSettled] = await Promise.allSettled([
    fetchFactorDiagnostic({ revalidate: 0, tags: ["factor-lab-diagnostic"] }),
    fetchFactorProposals("pending", {
      revalidate: 0,
      tags: ["factor-lab-pending"],
    }),
    fetchFactorProposals(undefined, {
      revalidate: 0,
      tags: ["factor-lab-history"],
    }),
  ]);

  const diagnostic =
    diagSettled.status === "fulfilled" ? diagSettled.value : null;
  const pending =
    pendingSettled.status === "fulfilled"
      ? pendingSettled.value.proposals
      : [];
  const all =
    allSettled.status === "fulfilled" ? allSettled.value.proposals : [];
  const history = all.filter((p) => p.status !== "pending");

  return (
    <TmScreen>
      {/* Section 1: Page header */}
      <TmPane title="FACTOR LAB">
        <div className="px-3 py-2.5">
          <p className="font-tm-mono text-[11px] text-tm-fg-2">
            Propose new factor expressions via LLM. Human-gated approval
            registers them as the live factor.custom_expression.
          </p>
        </div>
      </TmPane>

      {/* Section 2: Current live expression (intent: "what is running now?") */}
      <TmPane
        title="CURRENT LIVE EXPRESSION"
        meta={diagnostic ? "live" : "unavailable"}
      >
        <div className="px-3 py-2.5">
          {diagnostic ? (
            <pre className="overflow-x-auto rounded bg-tm-card p-3 font-mono text-[11px] text-tm-fg">
              {diagnostic.current_expression}
            </pre>
          ) : (
            <p className="font-tm-mono text-[11px] text-tm-neg">
              Failed to load current expression.
            </p>
          )}
        </div>
      </TmPane>

      {/* Section 3: Diagnostic snapshot (intent: "why might we want a new one?") */}
      <TmPane
        title="DIAGNOSTIC SNAPSHOT"
        meta={
          diagnostic
            ? diagnostic.weak_signal
              ? `weak: ${diagnostic.weak_signal}`
              : "no weak signal"
            : "unavailable"
        }
      >
        <div className="px-3 py-2.5 space-y-1">
          {diagnostic ? (
            <>
              <div className="font-tm-mono text-[11px] text-tm-fg-2">
                Weak signal:{" "}
                <strong className="text-tm-fg">
                  {diagnostic.weak_signal ?? "(none)"}
                </strong>{" "}
                {diagnostic.weak_signal_ic !== null && (
                  <span>
                    (IC = {diagnostic.weak_signal_ic.toFixed(4)})
                  </span>
                )}
              </div>
              {diagnostic.worst_fold_sharpe !== null && (
                <div className="font-tm-mono text-[11px] text-tm-fg-2">
                  Worst fold Sharpe:{" "}
                  <strong className="text-tm-neg">
                    {diagnostic.worst_fold_sharpe.toFixed(3)}
                  </strong>
                  {diagnostic.worst_fold_window && (
                    <span className="text-tm-muted">
                      {" "}
                      [{diagnostic.worst_fold_window[0]} to{" "}
                      {diagnostic.worst_fold_window[1]}]
                    </span>
                  )}
                </div>
              )}
              <div className="font-tm-mono text-[11px] text-tm-muted">
                {diagnostic.symptom_summary}
              </div>
            </>
          ) : (
            <p className="font-tm-mono text-[11px] text-tm-neg">
              Failed to load diagnostic.
            </p>
          )}
        </div>
      </TmPane>

      {/* Section 4: Propose (intent: "trigger the LLM to generate candidates") */}
      <TmPane title="PROPOSE NEW CANDIDATES">
        <div className="px-3 py-2.5">
          <ProposeButton n={5} />
        </div>
      </TmPane>

      {/* Section 5: Pending proposals (intent: "review + act on candidates") */}
      <TmPane
        title="PENDING PROPOSALS"
        meta={`${pending.length} pending`}
      >
        <div className="px-3 py-2.5">
          <PendingFactorProposalsTable proposals={pending} />
        </div>
      </TmPane>

      {/* Section 6: History (intent: "audit trail of past decisions") */}
      <TmPane
        title="HISTORY"
        meta={`${history.length} record${history.length !== 1 ? "s" : ""}`}
      >
        <div className="px-3 py-2.5">
          <FactorHistoryTable proposals={history} />
        </div>
      </TmPane>
    </TmScreen>
  );
}
