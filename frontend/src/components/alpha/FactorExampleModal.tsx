"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FactorExampleList } from "./FactorExampleList";
import type { FactorExample } from "./FactorExamples";

/**
 * FactorExampleModal — the example library collapsed behind the "Browse
 * examples" button (left of TRANSLATE & BACKTEST). Replaces the always-on
 * inline list that pushed the primary action down the card.
 *
 * The body is the existing <FactorExampleList>, which already carries the
 * search box + tier grouping + per-row metrics/expression/hypothesis, so the
 * modal is a thin overlay: centered panel, header, Esc / overlay-click close,
 * background scroll lock. Selecting a row loads the example and closes.
 */
interface Props {
  readonly open: boolean;
  readonly examples: ReadonlyArray<FactorExample>;
  readonly disabled: boolean;
  readonly onSelect: (ex: FactorExample) => void;
  readonly onClose: () => void;
}

export function FactorExampleModal({
  open,
  examples,
  disabled,
  onSelect,
  onClose,
}: Props) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);

  // Esc closes; lock the background scroll while open so the modal owns focus.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={tk("alpha.examples.modalTitle")}
      onClick={onClose}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-6 sm:p-10"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80vh] w-full max-w-[760px] flex-col border border-tm-rule-2 bg-tm-bg shadow-2xl"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-tm-rule px-4 py-3">
          <div className="min-w-0">
            <div className="font-tm-mono text-[13px] tracking-[0.06em] text-tm-accent">
              {tk("alpha.examples.modalTitle")}
            </div>
            <div className="mt-0.5 truncate text-[11px] text-tm-muted">
              {tk("alpha.examples.modalSub")}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="close"
            className="shrink-0 rounded p-1 text-tm-muted transition-colors hover:bg-tm-bg-3 hover:text-tm-fg"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        {/* Body — searchable, tier-grouped example list */}
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <FactorExampleList
            examples={examples}
            disabled={disabled}
            onSelect={onSelect}
          />
        </div>
      </div>
    </div>
  );
}
