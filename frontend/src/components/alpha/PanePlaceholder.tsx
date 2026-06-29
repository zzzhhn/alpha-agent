"use client";

/**
 * PanePlaceholder — the idle (pre-run) state for the three evidence panes.
 *
 * Distinct from <Skeleton>: a skeleton signals "data is loading right now",
 * so showing it before the user has run anything is dishonest (UI/UX #9). The
 * idle state is a quiet, dashed, non-animated hint that simply explains what
 * will appear here once a hypothesis is run.
 */
export function PanePlaceholder({ hint }: { readonly hint: string }) {
  return (
    <div className="flex flex-1 items-center rounded border border-dashed border-tm-rule/70 bg-tm-bg-3/30 px-3 py-6">
      <p className="font-tm-mono text-[11px] leading-relaxed text-tm-muted">
        {hint}
      </p>
    </div>
  );
}
