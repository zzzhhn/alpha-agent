"use client";

/**
 * TmField: canonical workstation form controls.
 *
 * Exports the canonical field family sharing the same label + hint typography
 * conventions:
 *
 *   - <TmInput>       text / password / number input
 *   - <TmSelect>      single-select dropdown
 *   - <TmFieldShell>  bare label + children wrapper, for callers that
 *                     need to inject a non-standard control (e.g. a
 *                     reveal-toggle next to a password input)
 *
 * All controls use the project's `--tm-*` token namespace, JetBrains Mono
 * for the input value (so monospace-aligned numbers render cleanly in
 * forms), and the design's hairline border/focus-accent pattern.
 *
 * Production pages should use this family instead of creating page-local
 * input, select, or textarea styling.
 */

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  type ReactNode,
} from "react";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";

type FieldSize = "sm" | "md";

const FIELD_BASE =
  "w-full border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none transition-colors placeholder:text-tm-muted hover:border-tm-rule-2 focus:border-tm-accent disabled:cursor-not-allowed disabled:bg-tm-bg-3 disabled:text-tm-muted disabled:opacity-70";

const FIELD_SIZE: Record<FieldSize, string> = {
  sm: "h-7",
  md: "h-8",
};

const LABEL_BASE = "text-[10px] font-semibold uppercase tracking-[0.06em] text-tm-muted";

interface TmFieldShellProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly required?: boolean;
  readonly htmlFor?: string;
  readonly hintId?: string;
  readonly errorId?: string;
  readonly className?: string;
  readonly children: ReactNode;
}

export function TmFieldShell({
  label,
  hint,
  error,
  required,
  htmlFor,
  hintId,
  errorId,
  className,
  children,
}: TmFieldShellProps) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      {label && (
        <label className={LABEL_BASE} htmlFor={htmlFor}>
          {label}
          {required ? <span className="ml-1 text-tm-neg">*</span> : null}
        </label>
      )}
      {children}
      {hint && (
        <p id={hintId} className="text-[10.5px] text-tm-muted">{hint}</p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-[10.5px] text-tm-neg">
          {error}
        </p>
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
  readonly error?: ReactNode;
  readonly fieldSize?: FieldSize;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly className?: string;
  readonly inputClassName?: string;
}

export const TmInput = forwardRef<HTMLInputElement, TmInputProps>(function TmInput(
  {
    label,
    hint,
    error,
    fieldSize = "md",
    value,
    onChange,
    className,
    inputClassName,
    type = "text",
    id,
    required,
    ...rest
  },
  ref,
) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <TmFieldShell
      label={label}
      hint={hint}
      error={error}
      required={required}
      htmlFor={controlId}
      hintId={hintId}
      errorId={errorId}
      className={className}
    >
      <input
        ref={ref}
        id={controlId}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={describedBy}
        className={clsx(
          FIELD_BASE,
          FIELD_SIZE[fieldSize],
          error && "border-tm-neg focus:border-tm-neg",
          inputClassName,
        )}
        {...rest}
      />
    </TmFieldShell>
  );
});

// ── TmNumberInput ───────────────────────────────────────────────────

type TmNumberInputBaseProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "value" | "onChange" | "className"
>;

interface TmNumberInputProps extends TmNumberInputBaseProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly fieldSize?: FieldSize;
  readonly value: number;
  readonly onChange: (next: number) => void;
  readonly suffix?: ReactNode;
  readonly className?: string;
  readonly inputClassName?: string;
}

export function TmNumberInput({
  label,
  hint,
  error,
  fieldSize = "md",
  value,
  onChange,
  suffix,
  className,
  inputClassName,
  id,
  required,
  ...rest
}: TmNumberInputProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <TmFieldShell
      label={label}
      hint={hint}
      error={error}
      required={required}
      htmlFor={controlId}
      hintId={hintId}
      errorId={errorId}
      className={className}
    >
      <div
        className={clsx(
          FIELD_BASE,
          FIELD_SIZE[fieldSize],
          "flex items-center gap-1",
          error && "border-tm-neg focus-within:border-tm-neg",
        )}
      >
        <input
          id={controlId}
          type="number"
          value={value}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isFinite(next)) onChange(next);
          }}
          required={required}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
          className={clsx(
            "min-w-0 flex-1 bg-transparent font-tm-mono text-[11px] tabular-nums text-tm-fg outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
            inputClassName,
          )}
          {...rest}
        />
        {suffix ? <span className="shrink-0 text-[10px] text-tm-muted">{suffix}</span> : null}
      </div>
    </TmFieldShell>
  );
}

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
  readonly error?: ReactNode;
  readonly fieldSize?: FieldSize;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly options: readonly TmSelectOption[];
  readonly className?: string;
  readonly selectClassName?: string;
}

export function TmSelect({
  label,
  hint,
  error,
  fieldSize = "md",
  value,
  onChange,
  options,
  className,
  selectClassName,
  id,
  required,
  ...rest
}: TmSelectProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <TmFieldShell
      label={label}
      hint={hint}
      error={error}
      required={required}
      htmlFor={controlId}
      hintId={hintId}
      errorId={errorId}
      className={className}
    >
      <div className="relative">
        <select
          id={controlId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={required}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
          className={clsx(
            FIELD_BASE,
            FIELD_SIZE[fieldSize],
            "appearance-none pr-7",
            error && "border-tm-neg focus:border-tm-neg",
            selectClassName,
          )}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value} className="bg-tm-bg-2 text-tm-fg">
              {o.label}
            </option>
          ))}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-tm-muted"
        />
      </div>
    </TmFieldShell>
  );
}

type TmTextareaBaseProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  "value" | "onChange" | "className"
>;

interface TmTextareaProps extends TmTextareaBaseProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly error?: ReactNode;
  readonly value: string;
  readonly onChange: (next: string) => void;
  readonly className?: string;
  readonly textareaClassName?: string;
}

export const TmTextarea = forwardRef<HTMLTextAreaElement, TmTextareaProps>(
  function TmTextarea(
    {
      label,
      hint,
      error,
      value,
      onChange,
      className,
      textareaClassName,
      id,
      required,
      rows = 4,
      ...rest
    },
    ref,
  ) {
    const generatedId = useId();
    const controlId = id ?? generatedId;
    const hintId = hint ? `${controlId}-hint` : undefined;
    const errorId = error ? `${controlId}-error` : undefined;
    const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
    return (
      <TmFieldShell
        label={label}
        hint={hint}
        error={error}
        required={required}
        htmlFor={controlId}
        hintId={hintId}
        errorId={errorId}
        className={className}
      >
        <textarea
          ref={ref}
          id={controlId}
          rows={rows}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          required={required}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={describedBy}
          className={clsx(
            FIELD_BASE,
            "min-h-20 resize-y py-2 leading-5",
            error && "border-tm-neg focus:border-tm-neg",
            textareaClassName,
          )}
          {...rest}
        />
      </TmFieldShell>
    );
  },
);

// ── TmRange ─────────────────────────────────────────────────────────

type TmRangeBaseProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "value" | "onChange" | "className" | "min" | "max" | "step"
>;

interface TmRangeProps extends TmRangeBaseProps {
  readonly label?: ReactNode;
  readonly hint?: ReactNode;
  readonly value: number;
  readonly onChange: (next: number) => void;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly formatValue?: (value: number) => ReactNode;
  readonly className?: string;
}

/** Canonical numeric slider with a visible value and keyboard-native semantics. */
export function TmRange({
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step = 1,
  formatValue = (current) => current,
  className,
  id,
  disabled,
  ...rest
}: TmRangeProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const progress = max === min ? 0 : ((value - min) / (max - min)) * 100;
  return (
    <TmFieldShell
      label={label}
      hint={hint}
      htmlFor={controlId}
      hintId={hintId}
      className={className}
    >
      <div className="flex min-h-8 items-center gap-3 border border-tm-rule bg-tm-bg-2 px-2 focus-within:border-tm-accent">
        <input
          id={controlId}
          type="range"
          value={value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          aria-describedby={hintId}
          onChange={(event) => onChange(Number(event.target.value))}
          style={{
            background: `linear-gradient(to right, var(--tm-accent) 0%, var(--tm-accent) ${progress}%, var(--tm-rule-2) ${progress}%, var(--tm-rule-2) 100%)`,
          }}
          className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-none outline-none disabled:cursor-not-allowed disabled:opacity-50 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-none [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-tm-fg [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-none [&::-webkit-slider-thumb]:bg-tm-fg"
          {...rest}
        />
        <output htmlFor={controlId} className="min-w-10 text-right font-tm-mono text-[10.5px] tabular-nums text-tm-fg">
          {formatValue(value)}
        </output>
      </div>
    </TmFieldShell>
  );
}

// ── TmCheckbox ──────────────────────────────────────────────────────

type TmCheckboxBaseProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type" | "checked" | "onChange" | "className"
>;

interface TmCheckboxProps extends TmCheckboxBaseProps {
  readonly checked: boolean;
  readonly onChange: (next: boolean) => void;
  readonly label: ReactNode;
  readonly hint?: ReactNode;
  readonly className?: string;
}

export function TmCheckbox({
  checked,
  onChange,
  label,
  hint,
  className,
  id,
  disabled,
  required,
  ...rest
}: TmCheckboxProps) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  return (
    <div className={clsx("flex min-w-0 flex-col gap-1", className)}>
      <label
        htmlFor={controlId}
        className={clsx(
          "flex min-h-8 cursor-pointer items-center gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg transition-colors hover:border-tm-rule-2",
          disabled && "cursor-not-allowed bg-tm-bg-3 text-tm-muted opacity-70",
        )}
      >
        <input
          id={controlId}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          aria-describedby={hintId}
          disabled={disabled}
          required={required}
          className="peer sr-only"
          {...rest}
        />
        <span
          aria-hidden="true"
          className={clsx(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] border border-tm-rule-2 bg-tm-bg text-[11px] font-semibold text-tm-bg peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-tm-accent",
            checked && "border-tm-accent bg-tm-accent",
          )}
        >
          {checked ? "✓" : ""}
        </span>
        <span className="min-w-0">{label}</span>
        {required ? <span className="text-tm-neg">*</span> : null}
      </label>
      {hint ? <p id={hintId} className="text-[10.5px] text-tm-muted">{hint}</p> : null}
    </div>
  );
}
