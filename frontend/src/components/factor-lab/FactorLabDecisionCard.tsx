import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import type { FactorDiagnosticSnapshot } from "@/lib/api/factor-lab";
import { LiveExpressionPanel } from "./LiveExpressionPanel";
import { WeakSignalPanel } from "./WeakSignalPanel";
import { SymptomCaption } from "./SymptomCaption";
import { ProposeActionRow } from "./ProposeActionRow";

interface FactorLabDecisionCardProps {
  readonly locale: Locale;
  readonly diagnostic: FactorDiagnosticSnapshot | null;
}

export function FactorLabDecisionCard({
  locale,
  diagnostic,
}: FactorLabDecisionCardProps) {
  const title = t(locale, "factorLab.decision.title");

  if (diagnostic === null) {
    return (
      <TmPane title={title}>
        <div className="flex flex-col gap-3 px-3 py-2.5">
          <p className="font-tm-mono text-[11px] text-tm-neg">
            {t(locale, "factorLab.decision.diagnosticUnavailable")}
          </p>
          <div>
            <ProposeActionRow n={5} />
          </div>
        </div>
      </TmPane>
    );
  }

  return (
    <TmPane title={title}>
      <div className="flex flex-col gap-3 px-3 py-2.5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <LiveExpressionPanel
            locale={locale}
            expression={diagnostic.current_expression}
            deployedAgoDays={null}
          />
          <WeakSignalPanel
            locale={locale}
            weakSignal={diagnostic.weak_signal}
            weakSignalIc={diagnostic.weak_signal_ic}
            worstFoldSharpe={diagnostic.worst_fold_sharpe}
            worstFoldWindow={diagnostic.worst_fold_window}
          />
        </div>
        <SymptomCaption locale={locale} symptom={diagnostic.symptom_summary} />
        <div>
          <ProposeActionRow n={5} />
        </div>
      </div>
    </TmPane>
  );
}
