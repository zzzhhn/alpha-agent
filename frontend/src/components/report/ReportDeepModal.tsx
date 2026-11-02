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
      <div className="report-chrome flex flex-wrap items-center justify-between gap-3 border-t border-tm-rule px-4 py-3">
        <p className="font-tm-mono text-xs text-tm-muted">{locale === "zh" ? "风险、收益分解、持仓与 IC 证据" : "Risk, return breakdown, holdings and IC evidence"}</p>
        <TmButton onClick={onOpen} size="md" variant="secondary" aria-haspopup="dialog">
          <LayoutGrid className="h-4 w-4" strokeWidth={1.75} />
          {tk("report.deep.fab")}
        </TmButton>
      </div>

      <TmDialog open={open} onClose={onClose} title={tk("report.deep.title")}
        description={tk("report.deep.meta")} closeLabel={locale === "zh" ? "关闭深度报告" : "Close detailed report"}
        className="!max-w-[1080px]" bodyClassName="flex flex-col gap-4">
        {children}
      </TmDialog>
      {/* Closed dialogs do not exist in the DOM. Retain every diagnostic in print. */}
      <div className="hidden print:block">{children}</div>
    </>
  );
}
