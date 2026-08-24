import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { TmButton } from "@/components/tm/TmButton";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly children: ReactNode;
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly icon?: ReactNode;
}

export function Button({
  children,
  variant = "secondary",
  size = "md",
  icon,
  className,
  ...props
}: ButtonProps) {
  return (
    <TmButton
      variant={variant}
      size={size}
      className={className}
      {...props}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </TmButton>
  );
}
