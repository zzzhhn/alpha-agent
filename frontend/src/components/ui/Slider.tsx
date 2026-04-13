"use client";

import clsx from "clsx";

interface SliderProps {
  readonly label: string;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly step?: number;
  readonly onChange: (value: number) => void;
  readonly unit?: string;
  readonly className?: string;
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  unit = "",
  className,
}: SliderProps) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      <div className="flex items-center justify-between">
        <label className="text-[11px] text-muted">{label}</label>
        <span className="font-mono text-xs font-semibold text-text">
          {value}
          {unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-accent"
      />
      <div className="flex justify-between text-[10px] text-muted">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}
