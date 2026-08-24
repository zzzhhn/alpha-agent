import type { ReactNode } from "react";

export interface DecisionMetric {
  readonly label: string;
  readonly value: ReactNode;
  readonly detail?: string;
  readonly tone?: "default" | "positive" | "warning" | "negative";
}

const TONE: Record<NonNullable<DecisionMetric["tone"]>, string> = {
  default: "text-tm-fg",
  positive: "text-tm-pos",
  warning: "text-tm-warn",
  negative: "text-tm-neg",
};

export function DecisionStrip({
  headline,
  description,
  metrics,
  action,
}: {
  readonly headline: ReactNode;
  readonly description?: string;
  readonly metrics: readonly DecisionMetric[];
  readonly action?: ReactNode;
}) {
  return (
    <section className="border-b border-tm-rule bg-tm-bg-2/35 px-4 py-4 lg:px-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-stretch xl:gap-5">
        <div className="flex min-w-0 flex-1 flex-col justify-center border-b border-tm-rule pb-4 xl:min-w-[260px] xl:border-b-0 xl:border-r xl:pb-0 xl:pr-5">
          <div className="text-[18px] font-semibold leading-6 text-tm-fg">{headline}</div>
          {description ? <p className="mt-1 text-[11px] leading-5 text-tm-muted">{description}</p> : null}
        </div>
        <div
          className="grid min-w-0 flex-[2] gap-px bg-tm-rule"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}
        >
          {metrics.map((metric) => (
            <div key={metric.label} className="min-w-0 bg-tm-bg px-3 py-3">
              <p className="font-tm-mono text-[10px] uppercase tracking-[0.06em] text-tm-muted">
                {metric.label}
              </p>
              <div className={`mt-1.5 font-tm-mono text-[18px] leading-none tabular-nums ${TONE[metric.tone ?? "default"]}`}>
                {metric.value}
              </div>
              {metric.detail ? <p className="mt-1.5 truncate text-[10px] text-tm-muted">{metric.detail}</p> : null}
            </div>
          ))}
        </div>
        {action ? <div className="flex shrink-0 items-center self-start xl:self-auto">{action}</div> : null}
      </div>
    </section>
  );
}
