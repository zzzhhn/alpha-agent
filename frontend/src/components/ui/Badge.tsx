import clsx from "clsx";
import type { ReactNode } from "react";

type BadgeVariant = "green" | "red" | "purple" | "yellow" | "muted";
type BadgeSize = "sm" | "md" | "lg";

interface BadgeProps {
  readonly children: ReactNode;
  readonly variant?: BadgeVariant;
  readonly size?: BadgeSize;
  readonly className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  green: "bg-[var(--badge-green-bg)] text-[var(--badge-green-text)]",
  red: "bg-[var(--badge-red-bg)] text-[var(--badge-red-text)]",
  purple:
    "bg-[var(--badge-purple-bg)] text-[var(--badge-purple-text)]",
  yellow: "bg-yellow/10 text-yellow",
  muted: "bg-border text-muted",
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-1.5 py-0.5 text-[12px]",
  md: "px-2.5 py-0.5 text-sm",
  lg: "px-5 py-1.5 text-[24px]",
};

export function Badge({
  children,
  variant = "muted",
  size = "md",
  className,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md font-semibold",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
    >
      {children}
    </span>
  );
}
