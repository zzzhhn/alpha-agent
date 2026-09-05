"use client";

import { LayoutGrid } from "lucide-react";
import { type ReactNode } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmButton } from "@/components/tm/TmButton";
import { TmDialog } from "@/components/tm/TmDialog";

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

  return (
    <>
      {/* Floating action button — always reachable while a report is open */}
      <TmButton
        onClick={onOpen}
        size="md"
        variant="secondary"
        className="fixed bottom-6 right-6 z-[55] px-4 shadow-[var(--tm-shadow-floating)]"
      >
        <LayoutGrid className="h-4 w-4" strokeWidth={1.75} />
        {tk("report.deep.fab")}
      </TmButton>

      <TmDialog open={open} onClose={onClose} title={tk("report.deep.title")}
        description={tk("report.deep.meta")} closeLabel={locale === "zh" ? "关闭深度报告" : "Close detailed report"}
        className="!max-w-[1080px]" bodyClassName="flex flex-col gap-4">
        {children}
      </TmDialog>
    </>
  );
}
