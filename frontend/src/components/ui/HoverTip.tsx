"use client";

import type { ReactNode } from "react";
import { TmTooltip } from "@/components/tm/TmTooltip";

/** Compatibility wrapper. New code should import TmTooltip directly. */
export function HoverTip({
  children,
  content,
  placement = "bottom",
  width = 224,
  className = "",
}: {
  children: ReactNode;
  content: string;
  placement?: "bottom" | "top";
  width?: number;
  className?: string;
}) {
  return (
    <TmTooltip
      content={content}
      placement={placement}
      width={width}
      className={className}
    >
      {children}
    </TmTooltip>
  );
}
