"use client";

import clsx from "clsx";

interface SelectOption {
  readonly value: string;
  readonly label: string;
}

interface SelectProps {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly options: readonly SelectOption[];
  readonly className?: string;
}

export function Select({
  label,
  value,
  onChange,
  options,
  className,
}: SelectProps) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      <label className="text-[13px] text-muted">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-border bg-card px-3 py-2 font-mono text-base text-text focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
