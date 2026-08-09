"use client";

/**
 * BacktestAnalyticsGroups (T6) — orchestrator for four grouped accordions
 * holding nine sub-pane wrappers. Per spec §7:
 *
 *   RISK DETAIL          — RiskAttribution + WorstDrawdowns + WinLossDistribution
 *   REGIME BREAKDOWN     — TrainTestSplit + RegimeBreakdown
 *   HOLDINGS             — PortfolioToday + PositionContribution
 *   OPERATIONS           — TurnoverProfile + DailyBreakdown
 *
 * Badge logic per spec §8.4:
 *   RISK badge ⚠ when maxDD < -0.25 (alert) OR hit_rate < 0.4 (warn)
 *   OPERATIONS badge ⚠ when turnover > 0.6 (warn)
 *   REGIME / HOLDINGS — no badge in v1
 *
 * T8 will mount this under the evidence grid on /backtest.
 */

import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { GroupAccordion, type GroupBadge } from "./GroupAccordion";
import { RiskAttributionPane } from "./RiskAttributionPane";
import { WorstDrawdownsPane } from "./WorstDrawdownsPane";
import { WinLossDistributionPane } from "./WinLossDistributionPane";
import { TrainTestSplitPane } from "./TrainTestSplitPane";
import { RegimeBreakdownPane } from "./RegimeBreakdownPane";
import { PortfolioTodayPane } from "./PortfolioTodayPane";
import { PositionContributionPane } from "./PositionContributionPane";
import { TurnoverProfilePane } from "./TurnoverProfilePane";
import { DailyBreakdownPane } from "./DailyBreakdownPane";
import type { Run } from "./types";

interface Props {
  readonly currentRun: Run | null;
}

const RISK_DRAWDOWN_THRESHOLD = -0.25;
const RISK_HIT_RATE_THRESHOLD = 0.4;
const OPERATIONS_TURNOVER_THRESHOLD = 0.6;

export function BacktestAnalyticsGroups({ currentRun }: Props) {
  const { locale } = useLocale();
  const hasDailyBreakdown = Boolean(currentRun?.raw.daily_breakdown?.length);
  const breakdownRequested = currentRun?.params.includeBreakdown === true;

  const riskBadge: GroupBadge | null = (() => {
    if (!currentRun) return null;
    const maxDD = currentRun.metrics.maxDD;
    const hitRate = currentRun.raw.test_metrics?.hit_rate;
    if (maxDD != null && maxDD < RISK_DRAWDOWN_THRESHOLD) {
      return {
        severity: "alert",
        reason: t(
          locale,
          "backtest.group.badgeDrawdown" as Parameters<typeof t>[1],
        ),
      };
    }
    if (hitRate != null && hitRate < RISK_HIT_RATE_THRESHOLD) {
      return {
        severity: "warn",
        reason: t(
          locale,
          "backtest.group.badgeWinRate" as Parameters<typeof t>[1],
        ),
      };
    }
    return null;
  })();

  const opsBadge: GroupBadge | null = (() => {
    if (!currentRun) return null;
    const turnover = currentRun.metrics.turnover;
    if (turnover != null && turnover > OPERATIONS_TURNOVER_THRESHOLD) {
      return {
        severity: "warn",
        reason: t(
          locale,
          "backtest.group.badgeTurnover" as Parameters<typeof t>[1],
        ),
      };
    }
    return null;
  })();

  return (
    <section className="grid gap-2" aria-label={t(locale, "backtest.group.riskDetail" as Parameters<typeof t>[1])}>
      <GroupAccordion
        title={t(locale, "backtest.group.riskDetail" as Parameters<typeof t>[1])}
        count={3}
        badge={riskBadge}
        defaultOpen={riskBadge !== null}
      >
          <>
            <RiskAttributionPane currentRun={currentRun} />
            <WorstDrawdownsPane currentRun={currentRun} />
            <WinLossDistributionPane currentRun={currentRun} />
          </>
      </GroupAccordion>
      <GroupAccordion
        title={t(locale, "backtest.group.regimeBreakdown" as Parameters<typeof t>[1])}
        count={2}
      >
          <>
            <TrainTestSplitPane currentRun={currentRun} />
            <RegimeBreakdownPane currentRun={currentRun} />
          </>
      </GroupAccordion>
      <GroupAccordion
        title={t(locale, "backtest.group.holdings" as Parameters<typeof t>[1])}
        count={hasDailyBreakdown ? 2 : 0}
      >
          {hasDailyBreakdown ? <>
            <PortfolioTodayPane currentRun={currentRun} />
            <PositionContributionPane currentRun={currentRun} />
          </> : <BreakdownEmptyState locale={locale} requested={breakdownRequested} />}
      </GroupAccordion>
      <GroupAccordion
        title={t(locale, "backtest.group.operations" as Parameters<typeof t>[1])}
        count={hasDailyBreakdown ? 2 : 0}
        badge={opsBadge}
        defaultOpen={riskBadge === null && opsBadge !== null}
      >
          {hasDailyBreakdown ? <>
            <TurnoverProfilePane currentRun={currentRun} />
            <DailyBreakdownPane currentRun={currentRun} />
          </> : <BreakdownEmptyState locale={locale} requested={breakdownRequested} />}
      </GroupAccordion>
    </section>
  );
}

function BreakdownEmptyState({
  locale,
  requested,
}: {
  readonly locale: "zh" | "en";
  readonly requested: boolean;
}) {
  return (
    <div className="grid min-h-[112px] grid-cols-[minmax(0,1fr)_280px] items-center gap-6 bg-tm-bg px-5 py-4">
      <div>
        <p className="text-[11px] font-semibold text-tm-fg">
          {locale === "zh"
            ? requested ? "后端未返回每日持仓明细" : "本次运行未请求每日持仓明细"
            : requested ? "The backend returned no daily breakdown" : "Daily breakdown was not requested for this run"}
        </p>
        <p className="mt-1 text-[10px] leading-5 text-tm-muted">
          {locale === "zh"
            ? requested
              ? "请求已包含明细开关，但数据源没有生成可用记录。请检查样本区间和候选股票覆盖后重跑。"
              : "这是为减少约 200 KB 响应体积而采用的默认设置，不是页面加载失败。"
            : requested
              ? "The request included breakdown data, but the source produced no usable rows. Check the sample window and ticker coverage."
              : "This is the bandwidth-saving default, not a page load failure."}
        </p>
      </div>
      <div className="border-l border-tm-rule pl-5 text-[10px] leading-5 text-tm-fg-2">
        <p className="font-semibold text-tm-accent">{locale === "zh" ? "如何获得数据" : "How to populate this section"}</p>
        <p>{locale === "zh" ? "展开顶部“高级”参数，开启“返回每日明细”，然后重新运行回测。" : "Open Advanced, enable Return daily breakdown, then rerun the backtest."}</p>
      </div>
    </div>
  );
}
