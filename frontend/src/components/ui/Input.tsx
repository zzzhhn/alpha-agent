"use client";

import clsx from "clsx";

interface InputProps {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly type?: "text" | "date" | "number";
  readonly placeholder?: string;
  readonly error?: string;
  readonly className?: string;
}

export function Input({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  error,
  className,
}: InputProps) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      <label className="text-[13px] text-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={clsx(
          "rounded-lg border bg-card px-3 py-2 font-mono text-base text-text",
          "placeholder:text-muted/50 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent",
          error ? "border-red" : "border-border"
        )}
      />
      {error && <span className="text-[12px] text-red">{error}</span>}
    </div>
  );
}
