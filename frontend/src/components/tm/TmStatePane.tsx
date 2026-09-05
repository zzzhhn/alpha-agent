"use client";

import { useId, type ReactNode } from "react";
import clsx from "clsx";
import { TmButton } from "./TmButton";

export type TmState =
  | "loading"
  | "empty"
  | "error"
  | "unauthorized"
  | "stale"
  | "partial";

export interface TmStatePaneAction {
  readonly label: ReactNode;
  readonly onClick: () => void;
  readonly disabled?: boolean;
  readonly loading?: boolean;
  readonly variant?: "primary" | "secondary" | "ghost";
}

export interface TmStatePaneProps {
  readonly state: TmState;
  readonly title: ReactNode;
  readonly description?: ReactNode;
  readonly action?: TmStatePaneAction;
  readonly className?: string;
}

interface StateStyle {
  readonly marker: string;
  readonly markerClassName: string;
  readonly markerBorderClassName: string;
  readonly borderClassName: string;
}

const STATE_STYLES: Record<TmState, StateStyle> = {
  loading: {
    marker: "…",
    markerClassName: "text-tm-info",
    markerBorderClassName: "border-tm-info",
    borderClassName: "border-tm-rule",
  },
  empty: {
    marker: "∅",
    markerClassName: "text-tm-muted",
    markerBorderClassName: "border-tm-rule-2",
    borderClassName: "border-tm-rule",
  },
  error: {
    marker: "!",
    markerClassName: "text-tm-neg",
    markerBorderClassName: "border-tm-neg",
    borderClassName: "border-tm-neg",
  },
  unauthorized: {
    marker: "⌁",
    markerClassName: "text-tm-warn",
    markerBorderClassName: "border-tm-warn",
    borderClassName: "border-tm-warn",
  },
  stale: {
    marker: "↻",
    markerClassName: "text-tm-warn",
    markerBorderClassName: "border-tm-warn",
    borderClassName: "border-tm-warn",
  },
  partial: {
    marker: "~",
    markerClassName: "text-tm-info",
    markerBorderClassName: "border-tm-info",
    borderClassName: "border-tm-info",
  },
};

/**
 * TmStatePane — stable-geometry surface for asynchronous and recoverable
 * content states. Titles, descriptions, and action labels are supplied by
 * the caller so locale-specific copy never lives in the primitive.
 */
export function TmStatePane({
  state,
  title,
  description,
  action,
  className,
}: TmStatePaneProps) {
  const titleId = useId();
  const descriptionId = useId();
  const style = STATE_STYLES[state];
  const role = state === "error" || state === "unauthorized" ? "alert" : "status";
  const actionBusy = action?.loading === true;

  return (
    <section
      aria-busy={state === "loading" || actionBusy || undefined}
      aria-describedby={
        description === undefined || description === null
          ? undefined
          : descriptionId
      }
      aria-labelledby={titleId}
      aria-live={role === "alert" ? "assertive" : "polite"}
      data-state={state}
      role={role}
      className={clsx(
        "flex min-h-[160px] min-w-0 items-center justify-center border bg-tm-bg-2 px-4 py-8 font-tm-mono rounded-[2px]",
        style.borderClassName,
        className,
      )}
    >
      <div className="flex min-w-0 max-w-[72rem] flex-col items-center gap-2 text-center">
        {state === "loading" ? (
          <span aria-hidden="true" className="flex items-center gap-1 py-1">
            <span className="h-1.5 w-6 animate-pulse bg-tm-info motion-reduce:animate-none" />
            <span className="h-1.5 w-3 animate-pulse bg-tm-info [animation-delay:120ms] motion-reduce:animate-none" />
            <span className="h-1.5 w-1.5 animate-pulse bg-tm-info [animation-delay:240ms] motion-reduce:animate-none" />
          </span>
        ) : (
          <span
            aria-hidden="true"
            className={clsx(
              "flex h-6 w-6 items-center justify-center border text-[13px] font-semibold leading-none rounded-[2px]",
              style.markerClassName,
              style.markerBorderClassName,
            )}
          >
            {style.marker}
          </span>
        )}

        <p id={titleId} className="text-xs font-semibold tracking-[0.04em] text-tm-fg">
          {title}
        </p>

        {description !== undefined && description !== null && (
          <p id={descriptionId} className="max-w-full break-words text-xs leading-5 text-tm-muted">
            {description}
          </p>
        )}

        {action && (
          <TmButton
            type="button"
            variant={action.variant ?? "secondary"}
            onClick={action.onClick}
            disabled={action.disabled}
            loading={action.loading}
            className="mt-1"
          >
            {action.label}
          </TmButton>
        )}
      </div>
    </section>
  );
}
