"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { TmDisclosureButton } from "@/components/tm/TmButton";
import { TmPane } from "@/components/tm/TmPane";
import { FactorHistoryTable } from "./FactorHistoryTable";
import type { FactorProposal } from "@/lib/api/factor-lab";

interface HistoryCollapsedSectionProps {
  readonly history: readonly FactorProposal[];
}

export function HistoryCollapsedSection({
  history,
}: HistoryCollapsedSectionProps) {
  const { locale } = useLocale();
  const [expanded, setExpanded] = useState(false);

  const zh = locale === "zh";

  return (
    <TmPane title={zh ? "方法论提案历史" : "Methodology proposal history"}>
      {history.length === 0 ? (
        <p className="px-3 py-2 text-xs text-tm-muted">{t(locale, "factorLab.history.empty")}</p>
      ) : <>
      <TmDisclosureButton
        expanded={expanded}
        onClick={() => setExpanded((e) => !e)}
        label={
          <span>
          {zh ? `已加载 ${history.length} 条已处理提案` : `${history.length} decided proposals loaded`}
          </span>
        }
        className="h-auto border-0 bg-transparent px-3 py-2.5 font-tm-mono text-xs text-tm-fg-2 hover:border-transparent hover:bg-tm-bg-3 hover:text-tm-fg"
      />
      {expanded ? (
        <div className="border-t border-tm-rule">
          <FactorHistoryTable proposals={history} />
        </div>
      ) : null}
      </>}
    </TmPane>
  );
}
