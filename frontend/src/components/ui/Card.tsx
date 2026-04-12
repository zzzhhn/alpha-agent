import { type ReactNode } from "react";
import clsx from "clsx";

interface CardProps {
  readonly children: ReactNode;
  readonly className?: string;
  readonly padding?: "sm" | "md" | "lg";
}

const paddingMap = {
  sm: "p-3",
  md: "p-5",
  lg: "p-6",
} as const;

export function Card({
  children,
  className,
  padding = "md",
}: CardProps) {
  return (
    <div
      className={clsx(
        "glass-card",
        paddingMap[padding],
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  readonly title: string;
  readonly icon?: ReactNode;
  readonly subtitle?: string;
  readonly actions?: ReactNode;
}

export function CardHeader({
  title,
  icon,
  subtitle,
  actions,
}: CardHeaderProps) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <div>
        <div className="flex items-center gap-2 text-[15px] font-semibold text-text">
          {icon && (
            <span className="text-base" aria-hidden="true">
              {icon}
            </span>
          )}
          {title}
        </div>
        {subtitle && (
          <p className="mt-0.5 text-xs text-muted">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
