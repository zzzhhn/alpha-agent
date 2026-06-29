"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { ZooEntry } from "@/lib/factor-zoo";

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
        <button
          type="button"
          onClick={handleGenerate}
          disabled={running || !staged}
          className="shrink-0 bg-tm-accent px-3.5 py-1.5 font-tm-mono text-[12px] font-semibold text-tm-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {tk("report.compare2.generate")}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2.5 px-3.5 py-2.5">
        <select
          value={staged}
          onChange={(e) => setStaged(e.target.value)}
          disabled={running || zoo.length === 0}
          className="min-w-[240px] cursor-pointer border border-tm-rule bg-tm-bg-3 px-2.5 py-1.5 font-tm-mono text-[12px] text-tm-accent outline-none focus:border-tm-accent disabled:opacity-50"
        >
          <option value="">{tk("report.compare2.pick")}</option>
          {zoo.map((z) => (
            <option key={z.id} value={z.name}>
              {z.name}
            </option>
          ))}
        </select>

        {compareName ? (
          <span className="inline-flex items-center gap-2 font-tm-mono text-[11px] text-tm-fg-2">
            {tk("report.compare2.current")}
            <span className="text-tm-info">{compareName}</span>
            <button
              type="button"
              onClick={onClear}
              className="border border-tm-rule px-1.5 py-px text-[10px] text-tm-muted transition-colors hover:border-tm-neg hover:text-tm-neg"
            >
              {tk("report.compare2.clear")}
            </button>
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
