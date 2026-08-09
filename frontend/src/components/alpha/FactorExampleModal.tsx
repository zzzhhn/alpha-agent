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
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-6 sm:p-10"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[84vh] w-full max-w-[1040px] flex-col border border-tm-rule-2 bg-tm-bg shadow-2xl"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-tm-rule bg-tm-bg-2/45 px-5 py-4">
          <div className="min-w-0">
            <div className="font-tm-mono text-[10px] uppercase tracking-[0.16em] text-tm-accent">
              {locale === "zh" ? "研究起点库" : "Research starting points"}
            </div>
            <div className="mt-1 text-[18px] font-semibold text-tm-fg">
              {tk("alpha.examples.modalTitle")}
            </div>
            <div className="mt-1 truncate text-[11px] text-tm-muted">
              {tk("alpha.examples.modalSub")}
            </div>
          </div>
          <div className="mr-5 hidden grid-cols-2 divide-x divide-tm-rule border-y border-tm-rule lg:grid">
            <div className="px-4 py-2 text-right"><p className="text-[9px] uppercase text-tm-muted">{locale === "zh" ? "示例" : "Examples"}</p><p className="mt-1 font-mono text-[14px] text-tm-fg">{examples.length}</p></div>
            <div className="px-4 py-2 text-right"><p className="text-[9px] uppercase text-tm-muted">{locale === "zh" ? "选择后" : "On select"}</p><p className="mt-1 text-[10px] text-tm-accent">{locale === "zh" ? "载入假设与参数" : "Load thesis + params"}</p></div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="close"
            className="shrink-0 border border-tm-rule p-2 text-tm-muted transition-colors hover:border-tm-accent hover:text-tm-fg"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        {/* Body — searchable, tier-grouped example list */}
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
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
