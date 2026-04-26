import clsx from "clsx";
import { type ButtonHTMLAttributes, type ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly children: ReactNode;
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly icon?: ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-white border-accent hover:brightness-110",
  secondary:
    "bg-[var(--toggle-bg)] text-text-secondary border-border hover:border-accent hover:text-accent",
  ghost:
    "bg-transparent text-muted border-transparent hover:bg-white/[0.03] hover:text-text-secondary",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1 text-[13px] rounded",
  md: "px-3 py-1.5 text-sm rounded-md",
};

export function Button({
  children,
  variant = "secondary",
  size = "md",
  icon,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center gap-1.5 border font-sans transition-all duration-200",
        variantStyles[variant],
        sizeStyles[size],
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </button>
  );
}
