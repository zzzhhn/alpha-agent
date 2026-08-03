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
    <section className="border-b border-tm-rule bg-tm-bg-2/35 px-6 py-4">
      <div className="flex items-stretch gap-5">
        <div className="flex min-w-[260px] flex-1 flex-col justify-center border-r border-tm-rule pr-5">
          <div className="text-[17px] font-semibold leading-6 text-tm-fg">{headline}</div>
          {description ? <p className="mt-1 text-[11px] leading-5 text-tm-muted">{description}</p> : null}
        </div>
        <div
          className="grid flex-[2] divide-x divide-tm-rule border border-tm-rule"
          style={{ gridTemplateColumns: `repeat(${metrics.length}, minmax(100px, 1fr))` }}
        >
          {metrics.map((metric) => (
            <div key={metric.label} className="min-w-0 bg-tm-bg px-4 py-3">
              <p className="font-tm-mono text-[9px] uppercase tracking-[0.1em] text-tm-muted">
                {metric.label}
              </p>
              <div className={`mt-1.5 font-mono text-[19px] leading-none ${TONE[metric.tone ?? "default"]}`}>
                {metric.value}
              </div>
              {metric.detail ? <p className="mt-1.5 truncate text-[9px] text-tm-muted">{metric.detail}</p> : null}
            </div>
          ))}
        </div>
        {action ? <div className="flex shrink-0 items-center">{action}</div> : null}
      </div>
    </section>
  );
}
