"use client";

/**
 * TmField — workstation-aesthetic form controls.
 *
 * Exports three components sharing the same label + hint typography
 * conventions:
 *
 *   - <TmInput>       text / password / number input
 *   - <TmSelect>      single-select dropdown
 *   - <TmFieldShell>  bare label + children wrapper, for callers that
 *                     need to inject a non-standard control (e.g. a
 *                     reveal-toggle next to a password input)
 *
 * All three use the project's `--tm-*` token namespace, JetBrains Mono
 * for the input value (so monospace-aligned numbers render cleanly in
 * forms), and the design's hairline border/focus-accent pattern.
 *
 * Built fresh rather than wrapping `ui/Input` / `ui/Select` so the
 * un-ported pages keep their existing components untouched. The two
 * sets coexist until Stage 5 consolidates.
 */

import {
  forwardRef,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type ReactNode,
} from "react";
import clsx from "clsx";

const FIELD_BASE =
  "h-8 w-full bg-tm-bg-2 border border-tm-rule px-2 text-[12px] font-tm-mono text-tm-fg outline-none transition-colors placeholder:text-tm-muted focus:border-tm-accent disabled:opacity-50";

const LABEL_BASE = "text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted";

interface TmFieldShellProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly className?: string;
  readonly children: ReactNode;
}

export function TmFieldShell({
  label,
  hint,
  className,
  children,
}: TmFieldShellProps) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      {label && <label className={LABEL_BASE}>{label}</label>}
      {children}
      {hint && (
        <p className="text-[10.5px] text-tm-muted">{hint}</p>
      )}
    </div>
  );
}

// ── TmInput ──────────────────────────────────────────────────────────

type TmInputBaseProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "className"
>;

interface TmInputProps extends TmInputBaseProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly className?: string;
  readonly inputClassName?: string;
}

export const TmInput = forwardRef<HTMLInputElement, TmInputProps>(function TmInput(
  { label, hint, value, onChange, className, inputClassName, type = "text", ...rest },
  ref,
) {
  return (
    <TmFieldShell label={label} hint={hint} className={className}>
      <input
        ref={ref}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={clsx(FIELD_BASE, inputClassName)}
        {...rest}
      />
    </TmFieldShell>
  );
});

// ── TmSelect ─────────────────────────────────────────────────────────

interface TmSelectOption {
  readonly value: string;
  readonly label: string;
}

type TmSelectBaseProps = Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "value" | "onChange" | "className"
>;

interface TmSelectProps extends TmSelectBaseProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly options: readonly TmSelectOption[];
  readonly className?: string;
}

export function TmSelect({
  label,
  hint,
  value,
  onChange,
  options,
  className,
  ...rest
}: TmSelectProps) {
  return (
    <TmFieldShell label={label} hint={hint} className={className}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={clsx(FIELD_BASE, "appearance-none pr-7")}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-tm-bg-2 text-tm-fg">
            {o.label}
          </option>
        ))}
      </select>
    </TmFieldShell>
  );
}
