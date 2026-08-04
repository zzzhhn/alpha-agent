"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import type { Run } from "./types";

function metric(value: number | null, kind: "number" | "percent" = "number"): string {
  if (value == null) return "—";
  return kind === "percent" ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
}

function RunSummary({ run, label, active }: { readonly run: Run | null; readonly label: string; readonly active?: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <div className={`min-w-0 border px-4 py-3 ${active ? "border-tm-accent bg-tm-accent/5" : "border-tm-rule bg-tm-bg"}`}>
      <div className="flex items-center justify-between gap-3">
        <p className={`text-[10px] uppercase tracking-[0.08em] ${active ? "text-tm-accent" : "text-tm-muted"}`}>{label}</p>
        {run ? <span className="text-[9px] text-tm-muted">#{run.id.slice(-6)}</span> : null}
      </div>
      {run ? (
        <>
          <p className="mt-2 truncate font-mono text-[11px] text-tm-fg" title={run.params.expression}>{run.params.expression}</p>
          <p className="mt-2 font-mono text-[10px] text-tm-fg-2">
            Sharpe {metric(run.metrics.sharpe)} · MaxDD {metric(run.metrics.maxDD, "percent")} · IC {run.metrics.ic == null ? "—" : run.metrics.ic.toFixed(4)} · {zh ? "换手" : "Turnover"} {metric(run.metrics.turnover, "percent")}
          </p>
        </>
      ) : (
        <p className="mt-2 text-[10px] text-tm-muted">{zh ? "尚无可比较运行" : "No comparable run yet"}</p>
      )}
    </div>
  );
}

export function BacktestComparisonTray({
  current,
  baseline,
  previous,
  baselinePinned,
}: {
  readonly current: Run;
  readonly baseline: Run | null;
  readonly previous: Run | null;
  readonly baselinePinned: boolean;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return (
    <section className="mt-3 grid grid-cols-[140px_repeat(3,minmax(0,1fr))] gap-2" aria-label={zh ? "运行比较托盘" : "Run comparison tray"}>
      <div className="flex items-center border border-tm-rule bg-tm-bg-2 px-4 text-[11px] font-semibold text-tm-fg-2">
        {zh ? "对比摘要" : "Comparison"}
      </div>
      <RunSummary run={current} label={zh ? "本次运行" : "Current run"} active />
      <RunSummary run={baseline} label={baselinePinned ? (zh ? "固定基线" : "Pinned baseline") : (zh ? "默认基线" : "Default baseline")} />
      <RunSummary run={previous} label={zh ? "上次运行" : "Previous run"} />
    </section>
  );
}
