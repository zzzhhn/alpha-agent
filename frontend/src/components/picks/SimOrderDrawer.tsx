// frontend/src/components/picks/SimOrderDrawer.tsx
"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { RatingCard } from "@/lib/api/picks";
import { useLocale } from "@/components/layout/LocaleProvider";
import SimOrderForm from "./SimOrderForm";
import { Disclaimer } from "./paper/PaperUi";
import { t } from "@/lib/i18n";

interface Props {
  readonly ticker: string;
  readonly card: RatingCard;
  readonly cash: number;
  readonly onClose: () => void;
  readonly onOrderPlaced: () => void;
}

// card.as_of is a full ISO timestamp (fetched_at.isoformat()); the date
// portion is what the backend's pick_date column (DATE) expects.
function pickDateFromAsOf(asOf: string): string | undefined {
  return /^\d{4}-\d{2}-\d{2}/.test(asOf) ? asOf.slice(0, 10) : undefined;
}

export default function SimOrderDrawer({ ticker, card, onClose, onOrderPlaced }: Props) {
  const { locale } = useLocale();
  const drawerRef = useRef<HTMLDivElement>(null);
  const pickDate = pickDateFromAsOf(card.as_of);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={locale === "zh" ? "模拟下单" : "Simulated Order"}
        className="fixed right-0 top-0 z-50 flex h-full w-80 flex-col border-l border-tm-rule bg-tm-bg shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-tm-rule px-4 py-3">
          <span className="font-tm-mono text-[13px] font-semibold tracking-wide text-tm-accent">
            {locale === "zh" ? "模拟下单" : "Simulated Order"}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-tm-muted hover:text-tm-fg"
            aria-label={t(locale, "sim.close")}
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <SimOrderForm
            fixedTicker={ticker}
            locale={locale}
            onPlaced={() => { onOrderPlaced(); onClose(); }}
            pickDate={pickDate}
            pickTicker={card.ticker}
          />
          <div className="mt-3">
            <Disclaimer />
          </div>
        </div>
      </div>
    </>
  );
}
