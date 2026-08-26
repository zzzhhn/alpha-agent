import type { ReactNode } from "react";

export interface WorkbenchStatus {
  readonly label: string;
  readonly value: string;
  readonly tone?: "default" | "positive" | "warning" | "negative";
}

const STATUS_TONE: Record<NonNullable<WorkbenchStatus["tone"]>, string> = {
  default: "text-tm-fg-2",
  positive: "text-tm-pos",
  warning: "text-tm-warn",
  negative: "text-tm-neg",
};

export function WorkbenchHeader({
  eyebrow,
  title,
  subtitle,
  statuses,
  action,
}: {
  readonly eyebrow?: string;
  readonly title: ReactNode;
  readonly subtitle: string;
  readonly statuses?: readonly WorkbenchStatus[];
  readonly action?: ReactNode;
}) {
  return (
    <header className="flex min-h-20 items-center gap-6 border-b border-tm-rule px-6 py-3">
      <div className="min-w-0 flex-1">
        {eyebrow ? (
          <p className="mb-1 font-tm-mono text-xs uppercase tracking-[0.16em] text-tm-accent">
            {eyebrow}
          </p>
        ) : null}
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="font-tm-serif text-[26px] font-semibold tracking-[-0.025em] text-tm-fg lg:text-[28px]">
            {title}
          </h1>
          <p className="text-[12px] text-tm-muted">{subtitle}</p>
        </div>
      </div>

      {statuses && statuses.length > 0 ? (
        <div className="hidden shrink-0 items-stretch divide-x divide-tm-rule border-y border-tm-rule xl:flex">
          {statuses.map((status) => (
            <div key={status.label} className="min-w-[118px] px-4 py-2 text-right">
              <p className="font-tm-mono text-xs uppercase tracking-[0.1em] text-tm-muted">
                {status.label}
              </p>
              <p className={`mt-1 font-tm-mono text-[12px] ${STATUS_TONE[status.tone ?? "default"]}`}>
                {status.value}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}
