"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { FactorExampleList } from "./FactorExampleList";
import type { FactorExample } from "./FactorExamples";
import { TmDialog } from "@/components/tm/TmDialog";

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

  return (
    <TmDialog
      open={open}
      onClose={onClose}
      closeLabel={locale === "zh" ? "关闭示例库" : "Close example library"}
      eyebrow={locale === "zh" ? "研究起点库" : "Research starting points"}
      title={tk("alpha.examples.modalTitle")}
      description={tk("alpha.examples.modalSub")}
      headerAside={
        <div className="mr-2 hidden grid-cols-2 divide-x divide-tm-rule border-y border-tm-rule lg:grid">
            <div className="px-4 py-2 text-right"><p className="text-xs uppercase text-tm-muted">{locale === "zh" ? "示例" : "Examples"}</p><p className="mt-1 font-mono text-[14px] text-tm-fg">{examples.length}</p></div>
            <div className="px-4 py-2 text-right"><p className="text-xs uppercase text-tm-muted">{locale === "zh" ? "选择后" : "On select"}</p><p className="mt-1 text-xs text-tm-accent">{locale === "zh" ? "载入假设与参数" : "Load thesis + params"}</p></div>
        </div>
      }
    >
      <FactorExampleList
        examples={examples}
        disabled={disabled}
        onSelect={onSelect}
      />
    </TmDialog>
  );
}
