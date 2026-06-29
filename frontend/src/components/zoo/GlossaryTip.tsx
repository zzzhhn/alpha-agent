"use client";

import type { ReactNode } from "react";
import { HoverTip } from "@/components/ui/HoverTip";
import { useLocale } from "@/components/layout/LocaleProvider";
import { glossaryText } from "@/lib/zoo-glossary";

/**
 * GlossaryTip — wraps an abbreviation / status code / cryptic icon so hovering
 * it reveals the plain-language definition from ZOO_GLOSSARY (locale-aware).
 *
 * Text terms get a dotted underline (the "there's more here" affordance);
 * icons pass underline={false} so only the cursor-help signals the tooltip.
 * Built on the portal-based HoverTip so it never gets clipped by a table /
 * grid cell with overflow.
 */
export function GlossaryTip({
  term,
  children,
  underline = true,
  width = 264,
  className = "",
}: {
  readonly term: string;
  readonly children?: ReactNode;
  readonly underline?: boolean;
  readonly width?: number;
  readonly className?: string;
}) {
  const { locale } = useLocale();
  const content = glossaryText(term, locale);
  return (
    <HoverTip content={content} width={width} className={className}>
      <span
        className={`cursor-help ${
          underline
            ? "border-b border-dotted border-tm-muted/60 hover:border-tm-fg"
            : ""
        }`}
      >
        {children ?? term}
      </span>
    </HoverTip>
  );
}
