"use client";

import { Info } from "lucide-react";
import { TmTooltip } from "@/components/tm/TmTooltip";

/** Compatibility wrapper. New code should import TmTooltip directly. */
export function InfoTooltip({
  content,
  iconSize = 12,
  placement = "bottom",
  ariaLabel = "More information",
  className = "",
}: {
  content: string;
  iconSize?: number;
  placement?: "bottom" | "right";
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <TmTooltip
      content={content}
      placement={placement}
      width={256}
      ariaLabel={ariaLabel}
      className={className}
    >
      <Info
        size={iconSize}
        aria-hidden="true"
        className="cursor-help text-tm-muted transition-colors hover:text-tm-fg"
      />
    </TmTooltip>
  );
}
