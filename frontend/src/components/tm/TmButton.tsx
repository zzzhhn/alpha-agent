"use client";

/**
 * TmButton: canonical workstation action button.
 *
 * Four variants:
 *   - "primary"  : solid accent green (tm-go pattern from the design CSS).
 *                  Used for the single "GO" action of a pane (Save, Run,
 *                  Translate, Generate).
 *   - "secondary": hairline-bordered ghost. Used for "Test connection",
 *                  "Cancel", and other support actions.
 *   - "ghost"    : transparent text-only. Used for "Clear", "Reset",
 *                  destructive-but-low-stakes actions.
 *   - "danger"   : explicit destructive action with negative semantics.
 *
 * Loading and disabled are separate states. Loading keeps both labels in the
 * same grid cell so the button width does not jump while work is in progress.
 */

import Link from "next/link";
import { forwardRef, type ButtonHTMLAttributes, type ComponentProps, type ReactNode } from "react";
import clsx from "clsx";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "xs" | "sm" | "md";

export interface TmButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: Variant;
  readonly size?: Size;
  readonly loading?: boolean;
  readonly loadingLabel?: string;
  readonly children: ReactNode;
}

export interface TmIconButtonProps
  extends Omit<TmButtonProps, "aria-label" | "children" | "loadingLabel"> {
  readonly label: string;
  readonly icon: ReactNode;
}

export interface TmDisclosureButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  readonly expanded: boolean;
  readonly label: ReactNode;
  readonly meta?: ReactNode;
}

export interface TmRowButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-tm-accent text-tm-bg hover:opacity-90 disabled:bg-tm-bg-3 disabled:text-tm-muted disabled:cursor-progress",
  secondary:
    "border border-tm-rule bg-tm-bg text-tm-fg-2 hover:border-tm-rule-2 hover:bg-tm-bg-2 hover:text-tm-fg disabled:text-tm-muted",
  ghost:
    "text-tm-muted hover:text-tm-fg disabled:opacity-50",
  danger:
    "border border-tm-neg bg-tm-neg-soft text-tm-neg hover:bg-tm-neg hover:text-tm-bg disabled:border-tm-rule disabled:bg-tm-bg-3 disabled:text-tm-muted",
};

const SIZES: Record<Size, string> = {
  xs: "h-6 px-2 text-[10px]",
  sm: "h-7 px-3 text-[11px]",
  md: "h-8 px-3 text-[11px]",
};

const BUTTON_BASE =
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap font-tm-mono font-semibold tracking-[0.06em] transition-colors disabled:cursor-not-allowed disabled:opacity-60";

function buttonClassName(
  variant: Variant,
  size: Size,
  className?: string,
  loading = false,
) {
  return clsx(
    BUTTON_BASE,
    SIZES[size],
    VARIANTS[variant],
    loading && "disabled:cursor-progress",
    className,
  );
}

export const TmButton = forwardRef<HTMLButtonElement, TmButtonProps>(function TmButton({
  variant = "primary",
  size = "sm",
  loading = false,
  loadingLabel,
  className,
  type = "button",
  disabled,
  children,
  ...rest
}: TmButtonProps, ref) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClassName(variant, size, className, loading)}
      {...rest}
    >
      <span className="grid min-w-0 place-items-center">
        <span
          aria-hidden={loading || undefined}
          className={clsx(
            "col-start-1 row-start-1 inline-flex items-center gap-1.5",
            loading && "invisible",
          )}
        >
          {children}
        </span>
        <span
          aria-hidden={!loading || undefined}
          className={clsx(
            "col-start-1 row-start-1 inline-flex items-center gap-1.5",
            !loading && "invisible",
          )}
        >
          <span
            className="h-1.5 w-1.5 animate-tm-pulse bg-current motion-reduce:animate-none"
            aria-hidden="true"
          />
          {loadingLabel ?? children}
        </span>
      </span>
    </button>
  );
});

export interface TmLinkButtonProps extends Omit<ComponentProps<typeof Link>, "className"> {
  readonly variant?: Variant;
  readonly size?: Size;
  readonly className?: string;
}

/** Navigation styled with the same hierarchy and geometry as actions. */
export function TmLinkButton({
  variant = "secondary",
  size = "sm",
  className,
  ...rest
}: TmLinkButtonProps) {
  return <Link className={buttonClassName(variant, size, className)} {...rest} />;
}

/** Compact icon-only action with a required accessible name. */
export const TmIconButton = forwardRef<HTMLButtonElement, TmIconButtonProps>(function TmIconButton({
  label,
  icon,
  title,
  size = "xs",
  variant = "ghost",
  className,
  ...rest
}: TmIconButtonProps, ref) {
  return (
    <TmButton
      ref={ref}
      aria-label={label}
      title={title ?? label}
      size={size}
      variant={variant}
      className={clsx("w-6 px-0", className)}
      {...rest}
    >
      {icon}
    </TmButton>
  );
});

/** Full-width disclosure row for optional evidence and advanced sections. */
export function TmDisclosureButton({
  expanded,
  label,
  meta,
  className,
  type = "button",
  ...rest
}: TmDisclosureButtonProps) {
  return (
    <button
      type={type}
      aria-expanded={expanded}
      className={clsx(
        "flex h-8 w-full items-center justify-between gap-3 border-y border-tm-rule bg-tm-bg-2 px-3 font-tm-mono text-[10px] font-semibold tracking-[0.06em] text-tm-fg-2 transition-colors hover:border-tm-rule-2 hover:text-tm-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-tm-accent",
        className,
      )}
      {...rest}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span
          aria-hidden="true"
          className={clsx("transition-transform motion-reduce:transition-none", expanded && "rotate-90")}
        >
          ▸
        </span>
        <span className="truncate">{label}</span>
      </span>
      {meta !== undefined && meta !== null ? (
        <span className="truncate font-normal normal-case tracking-normal text-tm-muted">{meta}</span>
      ) : null}
    </button>
  );
}

/**
 * Semantic full-row action for dense ledgers, tables, and disclosure headers.
 * Layout remains caller-owned; focus, hover, disabled, and keyboard semantics
 * stay consistent with the workstation control family.
 */
export const TmRowButton = forwardRef<HTMLButtonElement, TmRowButtonProps>(function TmRowButton({
  className,
  type = "button",
  children,
  ...rest
}: TmRowButtonProps, ref) {
  return (
    <button
      ref={ref}
      type={type}
      className={clsx(
        "w-full cursor-pointer text-left outline-none transition-colors hover:bg-tm-bg-2 focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-tm-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
