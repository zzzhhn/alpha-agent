"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ZooEntry } from "@/lib/factor-zoo";
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
  compareName,
  onCompare,
  onClear,
  running,
}: {
  readonly zoo: readonly ZooEntry[];
  readonly compareName: string | null;
  readonly onCompare: (entry: ZooEntry) => void;
  readonly onClear: () => void;
  readonly running: boolean;
}) {
  const { locale } = useLocale();
  const tk = (k: string) => t(locale, k as Parameters<typeof t>[1]);
  const [staged, setStaged] = useState<string>("");

  function handleGenerate() {
    const entry = zoo.find((z) => z.name === staged);
    if (entry) onCompare(entry);
  }

  return (
    <section className="border border-tm-rule bg-tm-bg-2">
      <div className="flex items-start justify-between gap-3 border-b border-tm-rule px-3.5 py-2.5">
        <div className="min-w-0">
          <div className="font-tm-mono text-[11px] font-semibold tracking-[0.1em] text-tm-accent">
            {tk("report.compare2.title")}
          </div>
          <p className="mt-1 max-w-2xl text-[11px] leading-relaxed text-tm-muted">
            {tk("report.compare2.subtitle")}
          </p>
        </div>
        <TmButton
          onClick={handleGenerate}
          disabled={running || !staged}
          className="shrink-0"
        >
          {tk("report.compare2.generate")}
        </TmButton>
      </div>

      <div className="flex flex-wrap items-center gap-2.5 px-3.5 py-2.5">
        <TmSelectMenu
          value={staged}
          onChange={setStaged}
          ariaLabel={tk("report.compare2.pick")}
          placeholder={tk("report.compare2.pick")}
          options={zoo.map((z) => ({ value: z.name, label: z.name }))}
          disabled={running || zoo.length === 0}
          size="md"
          buttonClassName="min-w-[240px] text-tm-accent"
        />

        {compareName ? (
          <span className="inline-flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg-2">
            {tk("report.compare2.current")}
            <span className="text-tm-info">{compareName}</span>
            <TmButton
              variant="secondary"
              size="xs"
              onClick={onClear}
              className="px-1.5 text-[10px] text-tm-muted hover:border-tm-neg hover:text-tm-neg"
            >
              {tk("report.compare2.clear")}
            </TmButton>
          </span>
        ) : (
          <span className="font-tm-mono text-[11px] text-tm-muted">
            {tk("report.compare2.none")}
          </span>
        )}
      </div>
    </section>
  );
}
