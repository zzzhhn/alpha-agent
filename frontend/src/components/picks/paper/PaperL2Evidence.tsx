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
  if (!summary) {
    return (
      <p className="border-t border-tm-rule px-3 py-3 font-tm-mono text-xs text-tm-muted">
        {t(locale, "sim.l2.accumulating")}
      </p>
    );
  }
  const continuous = summary.continuous_account;
  const strategic = summary.strategic_continuous_account;
  const exceptions = summary.exceptions;
  const exceptionCount = exceptions
    ? exceptions.unfilled + exceptions.exited + exceptions.stale_marks + exceptions.missing_marks
    : 0;
  return (
    <div className="border-t border-tm-rule px-3 py-3">
      <div className="mb-3 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2">
        <div className="font-tm-mono text-xs uppercase tracking-wide text-tm-muted">{locale === "zh" ? "连续份额级验证账户" : "Continuous share-level validation book"}</div>
        {continuous ? (
          <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="NAV" value={`$${Math.round(continuous.nav).toLocaleString("en-US")}`} />
            <Metric label={locale === "zh" ? "累计收益" : "Cumulative"} value={pct(continuous.cumulative_return)} />
            <Metric label={locale === "zh" ? "持仓 / 待执行" : "Positions / Pending"} value={`${continuous.positions} / ${continuous.pending_orders}`} />
            <Metric label={locale === "zh" ? "累计成本" : "Costs"} value={`$${continuous.transaction_costs.toFixed(2)}`} />
          </div>
        ) : <p className="mt-2 font-tm-mono text-xs text-tm-muted">{locale === "zh" ? "等待迁移后初始化，只从部署后的新推荐开始，绝不回填已知历史价格。" : "Awaiting initialization. It starts only from a new post-deployment recommendation and never backfills already-known prices."}</p>}
        {continuous?.status === "awaiting_forward_run" ? <p className="mt-2 font-tm-mono text-xs leading-4 text-tm-muted">{locale === "zh" ? `已建立前瞻边界 RUN #${continuous.start_after_run_id}，等待下一份完整推荐。` : `Forward boundary is RUN #${continuous.start_after_run_id}; waiting for the next complete recommendation.`}</p> : null}
        {strategic ? <p className="mt-2 border-t border-tm-rule pt-2 font-tm-mono text-xs leading-4 text-tm-muted">{locale === "zh" ? `战略 60 日独立账户：${strategic.status === "active" ? `${strategic.positions} 个持仓，收益 ${pct(strategic.cumulative_return)}` : `已在 RUN #${strategic.start_after_run_id} 建立边界，等待同政策新快照`}` : `Strategic 60d independent book: ${strategic.status === "active" ? `${strategic.positions} positions, ${pct(strategic.cumulative_return)}` : `forward boundary at RUN #${strategic.start_after_run_id}`}`}</p> : null}
      </div>
      {summary.status !== "ready" ? <p className="font-tm-mono text-xs text-tm-muted">{t(locale, "sim.l2.accumulating")}</p> : <>
      <div className="mb-2 font-tm-mono text-xs uppercase tracking-wide text-tm-muted">
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
        <p className="mt-2 font-tm-mono text-xs text-tm-muted">
          {t(locale, "sim.l2.sectors")} {summary.sector_exposure.slice(0, 3).map((row) => `${row.sector} ${(row.weight * 100).toFixed(1)}%`).join(" · ")}
        </p>
      ) : null}
      </>}
    </div>
  );
}
