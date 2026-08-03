"use client";

import type { L2Summary } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { Metric } from "./PaperUi";

function pct(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
}

export default function PaperL2Evidence({ summary }: { readonly summary: L2Summary | null }) {
  const { locale } = useLocale();
  if (!summary || summary.status !== "ready") {
    return (
      <p className="border-t border-tm-rule px-3 py-3 font-tm-mono text-[10px] text-tm-muted">
        {t(locale, "sim.l2.accumulating")}
      </p>
    );
  }
  const exceptions = summary.exceptions;
  const exceptionCount = exceptions
    ? exceptions.unfilled + exceptions.exited + exceptions.stale_marks + exceptions.missing_marks
    : 0;
  return (
    <div className="border-t border-tm-rule px-3 py-3">
      <div className="mb-2 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
        {t(locale, "sim.l2.title")} · {summary.periods ?? 0} {t(locale, "sim.l2.periods")}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label={t(locale, "sim.l2.net")} value={pct(summary.net_return)} />
        <Metric label="SPY" value={pct(summary.spy_return)} />
        <Metric label="RSP" value={pct(summary.rsp_return)} />
        <Metric label={t(locale, "sim.l2.drawdown")} value={pct(summary.max_drawdown)} />
        <Metric label="β SPY" value={summary.beta_spy == null ? "—" : summary.beta_spy.toFixed(2)} />
        <Metric label={t(locale, "sim.l2.turnover")} value={pct(summary.mean_turnover)} />
        <Metric label="5/10/20 bps" value={[5, 10, 20].map((bps) => pct(summary.cost_sensitivity?.[String(bps)])).join(" / ")} />
        <Metric label={t(locale, "sim.l2.exceptions")} value={String(exceptionCount)} />
      </div>
      {summary.sector_exposure.length > 0 ? (
        <p className="mt-2 font-tm-mono text-[10px] text-tm-muted">
          {t(locale, "sim.l2.sectors")} {summary.sector_exposure.slice(0, 3).map((row) => `${row.sector} ${(row.weight * 100).toFixed(1)}%`).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}
