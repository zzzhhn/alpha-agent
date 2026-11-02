"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ZooEntry } from "@/lib/factor-zoo";
import type { FactorExample } from "@/components/alpha/FactorExamples";
import { TmButton } from "@/components/tm/TmButton";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";

/**
 * ReportCompareBar (ALPHACORE design, report block lines 568-581) — the
 * "COMPARE A SECOND FACTOR" pane directly under the verdict hero. Pick another
 * saved factor from the dropdown and Generate to produce the side-by-side
 * comparison tear sheet (overlay equity, metric diff, correlation, overlap).
 */
export function ReportCompareBar({
  zoo,
  examples,
  primaryExpression,
  compareName,
  onCompare,
  onCompareExample,
  onClear,
  running,
}: {
  readonly zoo: readonly ZooEntry[];
  readonly examples: readonly FactorExample[];
  readonly primaryExpression: string;
  readonly compareName: string | null;
  readonly onCompare: (entry: ZooEntry) => void;
  readonly onCompareExample: (entry: FactorExample) => void;
  readonly onClear: () => void;
  readonly running: boolean;
}) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);
  const [staged, setStaged] = useState<string>("");

  function handleGenerate() {
    const example = examples.find((entry) => `example:${entry.name}` === staged && entry.expression !== primaryExpression);
    if (example) { onCompareExample(example); return; }
    const entry = zoo.find((entry) => `zoo:${entry.id}` === staged && entry.expression !== primaryExpression);
    if (entry) onCompare(entry);
  }

  const options = [
    ...examples.filter((entry) => entry.expression !== primaryExpression).map((entry) => ({ value: `example:${entry.name}`, label: entry.name, meta: locale === "zh" ? "历史示例" : "Historical example" })),
    ...zoo.filter((entry) => entry.expression !== primaryExpression).map((entry) => ({ value: `zoo:${entry.id}`, label: entry.name, meta: locale === "zh" ? "因子库" : "Saved factor" })),
  ];

  return (
    <section className="report-chrome border-b border-tm-rule bg-tm-bg-2">
      <div className="flex flex-wrap items-center gap-2.5 px-4 py-3">
        <TmSelectMenu
          value={staged}
          onChange={setStaged}
          ariaLabel={tk("report.compare2.pick")}
          placeholder={tk("report.compare2.pick")}
          options={options}
          disabled={running || options.length === 0}
          size="md"
          className="min-w-0 max-w-full"
          buttonClassName="w-full max-w-[360px] text-tm-fg"
        />

        <TmButton variant="secondary" onClick={handleGenerate} disabled={running || !options.some((option) => option.value === staged)}>
          {locale === "zh" ? "生成对比" : "Generate comparison"}
        </TmButton>

        {compareName ? (
          <span className="inline-flex items-center gap-2 font-tm-mono text-xs text-tm-fg-2">
            {tk("report.compare2.current")}
            <span className="text-tm-info">{compareName}</span>
            <TmButton
              variant="secondary"
              size="xs"
              onClick={onClear}
              className="px-1.5 text-xs text-tm-muted hover:border-tm-neg hover:text-tm-neg"
            >
              {tk("report.compare2.clear")}
            </TmButton>
          </span>
        ) : (
          <span className="font-tm-mono text-xs text-tm-muted">
            {tk("report.compare2.none")}
          </span>
        )}
      </div>
      <p className="px-4 pb-3 font-tm-mono text-xs text-tm-muted">{locale === "zh" ? "使用当前报告的参数快照，另行计算第二个因子；不会使用尚未运行的草稿参数。" : "Computes the second factor with the current report’s settings, not unrun draft settings."}</p>
    </section>
  );
}
