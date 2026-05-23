import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

interface WeakSignalPanelProps {
  readonly locale: Locale;
  readonly weakSignal: string | null;
  readonly weakSignalIc: number | null;
  readonly worstFoldSharpe: number | null;
  readonly worstFoldWindow: readonly [string, string] | null;
}

export function WeakSignalPanel({
  locale,
  weakSignal,
  weakSignalIc,
  worstFoldSharpe,
  worstFoldWindow,
}: WeakSignalPanelProps) {
  if (weakSignal === null) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
          {t(locale, "factorLab.decision.weakSignal")}
        </div>
        <div className="font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "factorLab.decision.noWeakSignal")}
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {t(locale, "factorLab.decision.weakSignal")}
      </div>
      <div className="font-tm-mono text-[12px] text-tm-warn">
        <strong>{weakSignal}</strong>
        {weakSignalIc != null ? (
          <span className="ml-2 font-mono text-tm-fg-2">
            ({t(locale, "factorLab.decision.ic")} = {weakSignalIc.toFixed(4)})
          </span>
        ) : null}
      </div>
      {worstFoldSharpe != null ? (
        <div className="font-tm-mono text-[11px] text-tm-fg-2">
          {t(locale, "factorLab.decision.worstFold")}:{" "}
          <strong className="font-mono text-tm-neg">{worstFoldSharpe.toFixed(3)}</strong>
          {worstFoldWindow ? (
            <span className="ml-2 text-tm-muted">
              [{worstFoldWindow[0]} {"→"} {worstFoldWindow[1]}]
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
