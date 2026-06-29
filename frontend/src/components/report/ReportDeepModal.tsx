"use client";

import { LayoutGrid, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

/**
 * ReportDeepModal (ALPHACORE design, report block lines 668-718) — collapses
 * the long tail of the tear sheet (recovery / yearly / monthly / holdings / IC
 * / exposure) behind a floating bottom-right button, so the main report stops
 * scrolling forever. The FAB opens a centered modal that holds those deep
 * sections in their own scroll container.
 */
export function ReportDeepModal({
  open,
  onOpen,
  onClose,
  children,
}: {
  readonly open: boolean;
  readonly onOpen: () => void;
  readonly onClose: () => void;
  readonly children: ReactNode;
}) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  return (
    <>
      {/* Floating action button — always reachable while a report is open */}
      <button
        type="button"
        onClick={onOpen}
        className="fixed bottom-7 right-7 z-[55] inline-flex items-center gap-2 bg-tm-accent px-4 py-3 font-tm-mono text-[12px] font-bold tracking-[0.04em] text-tm-bg shadow-[0_8px_24px_rgba(0,0,0,0.4)] transition-opacity hover:opacity-90"
      >
        <LayoutGrid className="h-4 w-4" strokeWidth={1.75} />
        {tk("report.deep.fab")}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={tk("report.deep.title")}
          onClick={onClose}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-6 sm:p-10"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="flex max-h-[84vh] w-full max-w-[1080px] flex-col border border-tm-rule-2 bg-tm-bg shadow-2xl"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-tm-rule px-4 py-3">
              <div className="flex items-baseline gap-3">
                <span className="font-tm-mono text-[13px] tracking-[0.06em] text-tm-accent">
                  {tk("report.deep.title")}
                </span>
                <span className="font-tm-mono text-[10px] text-tm-muted">
                  {tk("report.deep.meta")}
                </span>
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
            <div className="flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto p-4">
              {children}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
