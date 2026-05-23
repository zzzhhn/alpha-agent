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
    <div className="flex flex-col gap-3">
      <GroupAccordion
        title={t(
          locale,
          "backtest.group.riskDetail" as Parameters<typeof t>[1],
        )}
        count={3}
        badge={riskBadge}
      >
        <RiskAttributionPane currentRun={currentRun} />
        <WorstDrawdownsPane currentRun={currentRun} />
        <WinLossDistributionPane currentRun={currentRun} />
      </GroupAccordion>

      <GroupAccordion
        title={t(
          locale,
          "backtest.group.regimeBreakdown" as Parameters<typeof t>[1],
        )}
        count={2}
      >
        <TrainTestSplitPane currentRun={currentRun} />
        <RegimeBreakdownPane currentRun={currentRun} />
      </GroupAccordion>

      <GroupAccordion
        title={t(locale, "backtest.group.holdings" as Parameters<typeof t>[1])}
        count={2}
      >
        <PortfolioTodayPane currentRun={currentRun} />
        <PositionContributionPane currentRun={currentRun} />
      </GroupAccordion>

      <GroupAccordion
        title={t(
          locale,
          "backtest.group.operations" as Parameters<typeof t>[1],
        )}
        count={2}
        badge={opsBadge}
      >
        <TurnoverProfilePane currentRun={currentRun} />
        <DailyBreakdownPane currentRun={currentRun} />
      </GroupAccordion>
    </div>
  );
}
