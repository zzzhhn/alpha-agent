"use client";

import { useState, useMemo } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmDisclosureButton } from "@/components/tm/TmButton";
import { TmPane } from "@/components/tm/TmPane";
import { FactorHistoryTable } from "./FactorHistoryTable";
import type { FactorProposal } from "@/lib/api/factor-lab";

function withinDays(iso: string | null, days: number): boolean {
  if (iso === null) return false;
  const t0 = Date.parse(iso);
  if (Number.isNaN(t0)) return false;
  return Date.now() - t0 <= days * 24 * 60 * 60 * 1000;
}

interface HistoryCollapsedSectionProps {
  readonly history: readonly FactorProposal[];
}

export function HistoryCollapsedSection({
  history,
}: HistoryCollapsedSectionProps) {
  const { locale } = useLocale();
  const [expanded, setExpanded] = useState(false);

  const summary = useMemo(() => {
    const recent = history.filter((p) => withinDays(p.created_at, 30));
    return {
      n: recent.length,
      a: recent.filter((p) => p.status === "approved").length,
      r: recent.filter((p) => p.status === "rejected").length,
      // FactorProposal.status union has no "rolled_back" literal; honest 0.
      b: 0,
    };
  }, [history]);

  const summaryText = t(locale, "factorLab.history.summary30d")
    .replace("{n}", String(summary.n))
    .replace("{a}", String(summary.a))
    .replace("{r}", String(summary.r))
    .replace("{b}", String(summary.b));

  return (
    <TmPane title={t(locale, "factorLab.history.title")}>
      <TmDisclosureButton
        expanded={expanded}
        onClick={() => setExpanded((e) => !e)}
        label={
          <span>
          {history.length === 0
            ? t(locale, "factorLab.history.empty")
            : summaryText}
          </span>
        }
        className="h-auto border-0 bg-transparent px-3 py-2.5 font-tm-mono text-[11px] text-tm-fg-2 hover:border-transparent hover:bg-tm-bg-3 hover:text-tm-fg"
      />
      {expanded && history.length > 0 ? (
        <div className="border-t border-tm-rule px-3 py-2.5">
          <FactorHistoryTable proposals={history as FactorProposal[]} />
        </div>
      ) : null}
    </TmPane>
  );
}
