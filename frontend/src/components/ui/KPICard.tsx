"use client";

import clsx from "clsx";

type DeltaDirection = "up" | "down" | "neutral";

interface KPICardProps {
  readonly label: string;
  readonly value: string | number;
  readonly subtitle?: string;
  readonly tooltip?: string;
  readonly delta?: {
    readonly value: string;
    readonly direction: DeltaDirection;
  };
  readonly status?: "green" | "yellow" | "red";
}

const statusDotColors = {
  green: "bg-green",
  yellow: "bg-yellow",
  red: "bg-red",
} as const;

const deltaColors = {
  up: "text-green",
  down: "text-red",
  neutral: "text-muted",
} as const;

const deltaArrows = {
  up: "\u2191",
  down: "\u2193",
  neutral: "\u2022",
} as const;

export function KPICard({
  label,
  value,
  subtitle,
  tooltip,
  delta,
  status,
}: KPICardProps) {
  return (
    <div
      className="glass-inner p-3"
      title={tooltip}
      role="group"
      aria-label={label}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[13px] text-muted">{label}</span>
        {status && (
          <span
            className={clsx(
              "h-2 w-2 rounded-full",
              statusDotColors[status]
            )}
            aria-label={`Status: ${status}`}
          />
        )}
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-mono text-xl font-bold text-text">
          {value}
        </span>
        {delta && (
          <span
            className={clsx(
              "font-mono text-sm font-semibold",
              deltaColors[delta.direction]
            )}
          >
            {deltaArrows[delta.direction]} {delta.value}
          </span>
        )}
      </div>

      {subtitle && (
        <p className="mt-1 text-[13px] text-muted">{subtitle}</p>
      )}
    </div>
  );
}
