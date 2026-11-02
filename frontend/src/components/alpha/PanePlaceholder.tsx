"use client";

/**
 * PanePlaceholder — the idle (pre-run) state for the three evidence panes.
 *
 * Distinct from <Skeleton>: a skeleton signals "data is loading right now",
 * so showing it before the user has run anything is dishonest (UI/UX #9). The
 * idle state is a quiet, compact, non-animated hint that simply explains what
 * will appear here once a hypothesis is run.
 */
export function PanePlaceholder({ hint }: { readonly hint: string }) {
  return (
    <div className="flex flex-1 items-center border-t border-tm-rule py-4">
      <p className="max-w-sm text-sm leading-6 text-tm-muted">
        {hint}
      </p>
    </div>
  );
}
