"use client";

import {
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import clsx from "clsx";

export interface TmToggleOption<K extends string> {
  readonly value: K;
  readonly label: ReactNode;
  readonly ariaLabel?: string;
  readonly disabled?: boolean;
}

export interface TmToggleGroupProps<K extends string> {
  readonly value: K;
  readonly options: ReadonlyArray<TmToggleOption<K>>;
  readonly onChange: (value: K) => void;
  readonly ariaLabel: string;
  readonly size?: "xs" | "sm";
  readonly orientation?: "horizontal" | "vertical";
  readonly className?: string;
}

const SIZE_STYLES = {
  xs: "h-6 px-2 text-xs",
  sm: "h-7 px-2.5 text-xs",
} as const;

/**
 * TmToggleGroup is the canonical exclusive compact selector.
 *
 * It uses radio semantics and roving focus so locale, theme, view, and filter
 * selectors behave consistently with a mouse, keyboard, and screen reader.
 */
export function TmToggleGroup<K extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  size = "xs",
  orientation = "horizontal",
  className,
}: TmToggleGroupProps<K>) {
  const generatedId = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function choose(index: number) {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    refs.current[index]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const previousKey = orientation === "vertical" ? "ArrowUp" : "ArrowLeft";
    const nextKey = orientation === "vertical" ? "ArrowDown" : "ArrowRight";
    if (![previousKey, nextKey, "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const enabled = options
      .map((option, index) => ({ option, index }))
      .filter(({ option }) => !option.disabled)
      .map(({ index }) => index);
    if (enabled.length === 0) return;

    const currentIndex = Math.max(0, options.findIndex((option) => option.value === value));
    const enabledPosition = Math.max(0, enabled.indexOf(currentIndex));
    if (event.key === "Home") return choose(enabled[0]);
    if (event.key === "End") return choose(enabled[enabled.length - 1]);
    const delta = event.key === nextKey ? 1 : -1;
    const nextPosition = (enabledPosition + delta + enabled.length) % enabled.length;
    choose(enabled[nextPosition]);
  }

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      aria-orientation={orientation}
      onKeyDown={onKeyDown}
      className={clsx(
        "inline-flex shrink-0 overflow-hidden rounded-[2px] border border-tm-rule bg-tm-bg-2",
        orientation === "vertical" && "flex-col",
        className,
      )}
    >
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            ref={(element) => {
              refs.current[index] = element;
            }}
            id={`${generatedId}-${option.value}`}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.ariaLabel}
            tabIndex={selected ? 0 : -1}
            disabled={option.disabled}
            onClick={() => choose(index)}
            className={clsx(
              "inline-flex cursor-pointer items-center justify-center whitespace-nowrap font-tm-mono font-semibold tracking-[0.04em] transition-colors disabled:cursor-not-allowed disabled:opacity-50",
              orientation === "horizontal"
                ? "border-r border-tm-rule last:border-r-0"
                : "w-full justify-start border-b border-tm-rule last:border-b-0",
              SIZE_STYLES[size],
              selected
                ? "bg-tm-accent-soft text-tm-accent"
                : "text-tm-muted hover:bg-tm-bg-3 hover:text-tm-fg",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
