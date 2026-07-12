"use client";

/**
 * PaperTradingModal — portal-based overlay for 模拟仓 / Paper Trading.
 *
 * Opens over the picks page without replacing it; closing instantly restores
 * the picks view (fixes the "can't get back" UX bug of the old inline swap).
 *
 * Closes on: X button, backdrop click, Escape key.
 * Body scroll is locked while open.
 */
import { useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import PaperTab from "./PaperTab";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

export default function PaperTradingModal({
  open,
  onClose,
  onPositionsChange,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onPositionsChange?: (positions: ReadonlyMap<string, number>) => void;
}) {
  const { locale } = useLocale();
  const title = t(locale, "sim.modal_title");

  // Escape key + body scroll lock
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prev;
    };
  }, [open, handleKey]);

  if (!open) return null;

  const modal = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 sm:p-8"
      onClick={onClose}
    >
      {/* Panel — stop propagation so clicks inside don't close */}
      <div
        className="flex max-h-[85vh] w-full max-w-5xl flex-col border border-tm-rule-2 bg-tm-bg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-tm-rule px-4 py-3">
          <div className="flex items-baseline gap-3">
            <span className="font-tm-mono text-[13px] font-semibold tracking-[0.06em] text-tm-accent">
              {title}
            </span>
            <span className="font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
              {locale === "zh" ? "模拟交易·T+1 成交" : "Simulated · T+1 fills"}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={locale === "zh" ? "关闭" : "Close"}
            className="shrink-0 rounded p-1.5 text-tm-muted transition-colors hover:bg-tm-bg-3 hover:text-tm-fg focus:outline-none focus:ring-1 focus:ring-tm-accent"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <PaperTab onPositionsChange={onPositionsChange} />
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
