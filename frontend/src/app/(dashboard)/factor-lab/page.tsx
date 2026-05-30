import { getServerLocale } from "@/lib/server-locale";
import { TmScreen } from "@/components/tm/TmPane";
import {
  fetchFactorDiagnostic,
  fetchFactorProposals,
} from "@/lib/api/factor-lab";
import { FactorLabDecisionCard } from "@/components/factor-lab/FactorLabDecisionCard";
import { PendingProposalsSection } from "@/components/factor-lab/PendingProposalsSection";
import { HistoryCollapsedSection } from "@/components/factor-lab/HistoryCollapsedSection";

// Force dynamic so that each request fetches fresh proposal state.
// This matches how /evolution handles proposals (revalidate: 0).
export const dynamic = "force-dynamic";

export default async function FactorLabPage() {
  const locale = await getServerLocale();

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
    pendingSettled.status === "fulfilled" ? pendingSettled.value.proposals : [];
  const all =
    allSettled.status === "fulfilled" ? allSettled.value.proposals : [];
  const history = all.filter((p) => p.status !== "pending");
  const liveExpression = diagnostic?.current_expression ?? "";

  return (
    <TmScreen>
      <FactorLabDecisionCard locale={locale} diagnostic={diagnostic} />
      <PendingProposalsSection
        proposals={pending}
        liveExpression={liveExpression}
      />
      <HistoryCollapsedSection history={history} />
    </TmScreen>
  );
}
