import { t } from "@/lib/i18n";
import type { Locale } from "@/lib/i18n";

interface LiveExpressionPanelProps {
  readonly locale: Locale;
  readonly expression: string;
  readonly deployedAgoDays?: number | null;
}

export function LiveExpressionPanel({
  locale,
  expression,
  deployedAgoDays,
}: LiveExpressionPanelProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {t(locale, "factorLab.decision.liveExpression")}
      </div>
      <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2.5 font-mono text-[11px] text-tm-fg">
        {expression}
      </pre>
      {deployedAgoDays != null ? (
        <div className="font-tm-mono text-[10px] text-tm-muted">
          {t(locale, "factorLab.decision.deployedAgo").replace("{n}", String(deployedAgoDays))}
        </div>
      ) : null}
    </div>
  );
}
