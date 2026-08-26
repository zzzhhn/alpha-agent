"use client";

/**
 * TmPane + TmScreen — workstation layout primitives (Variation C).
 *
 * `TmScreen` is the page-level container. It establishes the
 * "workstation floor" (`bg-tm-bg`) so trailing space below the last
 * pane reads as continuous floor rather than as an unfilled grid cell.
 * Children stack vertically with no gap; each pane brings its own
 * `border-bottom` hairline that separates it from the next.
 *
 * `TmPane` is a flat content section. Unlike the legacy rounded-card
 * pattern, panes have NO outer border; the `border-b border-tm-rule`
 * comes from the parent screen's child selector (or an explicit prop
 * for cases where the pane stands alone). Header is the only thing
 * with an explicit border-bottom — it always separates from the body.
 *
 * Two-col side-by-side panes use the sibling `<TmCols2>` container,
 * which divides space with a single internal `border-r` hairline.
 *
 * Source of truth: styles-screens.css `.tm-screen / .tm-pane / .tm-cols-2`.
 */

import { type ReactNode } from "react";
import clsx from "clsx";
import { useLocale } from "@/components/layout/LocaleProvider";

const LEGACY_TECHNICAL_TITLES: Readonly<Record<string, { readonly zh: string; readonly en: string }>> = {
  "HYPOTHESIS.INPUT": { zh: "研究假设", en: "Hypothesis input" },
  "FACTOR.EXAMPLES": { zh: "因子示例", en: "Factor examples" },
  "ERROR": { zh: "错误", en: "Error" },
  "COMPARE.OVERLAY": { zh: "对比叠加", en: "Comparison overlay" },
  "EQUITY.CURVE": { zh: "净值曲线", en: "Equity curve" },
  "REPORT.COMPARE": { zh: "报告对比", en: "Report comparison" },
  "USAGE": { zh: "使用说明", en: "Usage" },
  "REPORT.PICKER": { zh: "报告选择", en: "Report picker" },
  "REPORT.COVER": { zh: "报告封面", en: "Report cover" },
  "RISK.METRICS": { zh: "风险指标", en: "Risk metrics" },
  "TAIL.RISK": { zh: "尾部风险", en: "Tail risk" },
  "YEARLY.BREAKDOWN": { zh: "年度分解", en: "Yearly breakdown" },
  "COMPARE.METRICS": { zh: "指标对比", en: "Metric comparison" },
  "COMPARE.CORRELATION": { zh: "相关性对比", en: "Correlation comparison" },
  "RECENT.MOMENTUM": { zh: "近期动量", en: "Recent momentum" },
  "TICKER.OVERLAP": { zh: "标的重叠", en: "Ticker overlap" },
  "RECOVERY.STATS": { zh: "恢复统计", en: "Recovery statistics" },
  "ZOO.OVERVIEW": { zh: "因子库概览", en: "Factor zoo overview" },
  "PERF.DIST": { zh: "绩效分布", en: "Performance distribution" },
  "DECAY.ALERTS": { zh: "衰减警报", en: "Decay alerts" },
  "STALE.FACTORS": { zh: "过期因子", en: "Stale factors" },
  "CORRELATION": { zh: "相关性", en: "Correlation" },
  "OPS.USAGE": { zh: "运算符使用", en: "Operator usage" },
  "DIR.MIX": { zh: "方向分布", en: "Direction mix" },
  "TIMELINE.ACTIVITY": { zh: "时间线活动", en: "Timeline activity" },
  "ZOO.CATALOG": { zh: "因子库目录", en: "Factor zoo catalog" },
  "SIGNAL IC TREND": { zh: "信号 IC 趋势", en: "Signal IC trend" },
  "CONFIDENCE CALIBRATION": { zh: "置信度校准", en: "Confidence calibration" },
  "ADAPTIVE WEIGHTS": { zh: "自适应权重", en: "Adaptive weights" },
  "CHANGE HISTORY": { zh: "变更历史", en: "Change history" },
  "METHODOLOGY PROPOSALS": { zh: "方法论提案", en: "Methodology proposals" },
  "FACTOR LAB": { zh: "因子实验室", en: "Factor lab" },
  "CURRENT LIVE EXPRESSION": { zh: "当前生效表达式", en: "Current live expression" },
  "DIAGNOSTIC SNAPSHOT": { zh: "诊断快照", en: "Diagnostic snapshot" },
  "PROPOSE NEW CANDIDATES": { zh: "提出新候选", en: "Propose new candidates" },
  "PENDING PROPOSALS": { zh: "待审提议", en: "Pending proposals" },
  "HISTORY": { zh: "历史", en: "History" },
  "PANEL.OVERVIEW": { zh: "面板概览", en: "Panel overview" },
  "DATA.PIPELINE": { zh: "数据管线", en: "Data pipeline" },
  "AVAILABLE.SECTORS": { zh: "可用板块", en: "Available sectors" },
  "BIAS.GUARDS": { zh: "偏差防护", en: "Bias guards" },
  "PANEL.SCHEMA": { zh: "面板结构", en: "Panel schema" },
  "OPS.OVERVIEW": { zh: "运算符概览", en: "Operator overview" },
  "OPS.CATALOG": { zh: "运算符目录", en: "Operator catalog" },
  "METRICS.OVERVIEW": { zh: "指标概览", en: "Metrics overview" },
  "METRICS.CATALOG": { zh: "指标目录", en: "Metrics catalog" },
  "PORTFOLIO.RULES": { zh: "组合规则", en: "Portfolio rules" },
  "FACTOR.EXPRESSION": { zh: "因子表达式", en: "Factor expression" },
  "SETTINGS / BYOK": { zh: "设置与自备密钥", en: "Settings and BYOK" },
  "CREDENTIALS": { zh: "凭据", en: "Credentials" },
  "NOTES": { zh: "备注", en: "Notes" },
  "SIGNAL WEIGHTS OVERRIDE": { zh: "信号权重覆盖", en: "Signal weight override" },
  "WATCHLIST": { zh: "自选列表", en: "Watchlist" },
  "CHANGE LOG": { zh: "变更日志", en: "Change log" },
  "MINING.BRIEFING": { zh: "挖掘简报", en: "Mining briefing" },
  "MINING.JOURNAL": { zh: "挖掘日志", en: "Mining journal" },
  "SIGNAL.FORM": { zh: "信号配置", en: "Signal configuration" },
  "DATA.SOURCES": { zh: "数据源", en: "Data sources" },
  "OPERATOR.CATALOG": { zh: "运算符目录", en: "Operator catalog" },
  "WORST.DRAWDOWNS": { zh: "最大回撤区间", en: "Worst drawdowns" },
  "WORLDQUANT.BRAIN": { zh: "WorldQuant BRAIN", en: "WorldQuant BRAIN" },
  "WIN/LOSS.DISTRIBUTION": { zh: "盈亏分布", en: "Win/loss distribution" },
  "PORTFOLIO.TODAY": { zh: "今日持仓", en: "Portfolio today" },
  "MONTHLY.RETURNS": { zh: "月度收益", en: "Monthly returns" },
  "IC.TIMESERIES": { zh: "IC 时间序列", en: "IC timeseries" },
  "EXPOSURE": { zh: "敞口", en: "Exposure" },
  "SIGNAL.TODAY": { zh: "今日信号", en: "Signal today" },
  "DRAWDOWN.UNDERWATER": { zh: "水下回撤", en: "Drawdown underwater" },
  "TRAIN/TEST.SPLIT": { zh: "训练与测试划分", en: "Train/test split" },
  "POSITION.CONTRIBUTION": { zh: "持仓贡献", en: "Position contribution" },
  "RISK.ATTRIBUTION": { zh: "风险归因", en: "Risk attribution" },
  "TURNOVER.PROFILE": { zh: "换手特征", en: "Turnover profile" },
  "REGIME.BREAKDOWN": { zh: "市场状态分解", en: "Regime breakdown" },
  "BACKTEST.FORM": { zh: "回测配置", en: "Backtest configuration" },
  "EQUITY.UNDERWATER": { zh: "净值与水下回撤", en: "Equity and underwater" },
  "BACKTEST.KPI": { zh: "回测指标", en: "Backtest KPIs" },
  "DAILY.BREAKDOWN": { zh: "每日明细", en: "Daily breakdown" },
};

interface TmScreenProps {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmScreen({ children, className }: TmScreenProps) {
  return (
    <div
      className={clsx(
        "flex h-full min-h-0 min-w-0 flex-col bg-tm-bg",
        // Each direct pane child contributes its own bottom hairline so
        // the workstation floor (the empty area below the last pane) is
        // continuous, not boxed.
        "[&>*:not(:last-child)]:border-b [&>*:not(:last-child)]:border-tm-rule",
        className,
      )}
    >
      {children}
    </div>
  );
}

interface TmPaneProps {
  readonly title?: ReactNode;
  readonly meta?: ReactNode;
  readonly children?: ReactNode;
  readonly className?: string;
  readonly bodyClassName?: string;
  /** When true, the pane gets its own outer border (for use OUTSIDE a
   *  TmScreen — e.g. a standalone modal or a centred config panel). The
   *  default false is what every screen uses. */
  readonly standalone?: boolean;
}

export function TmPane({
  title,
  meta,
  children,
  className,
  bodyClassName,
  standalone = false,
}: TmPaneProps) {
  const { locale } = useLocale();
  const localizedTitle = typeof title === "string" && LEGACY_TECHNICAL_TITLES[title]
    ? LEGACY_TECHNICAL_TITLES[title][locale]
    : title;
  return (
    <section
      className={clsx(
        "flex flex-col bg-tm-bg",
        standalone && "border border-tm-rule",
        className,
      )}
    >
      {(localizedTitle || meta) && (
        <header className="flex items-center justify-between gap-3 border-b border-tm-rule bg-tm-bg-2 px-3 py-1.5 font-tm-mono text-xs">
          <span className="font-semibold uppercase tracking-[0.06em] text-tm-accent">
            {localizedTitle}
          </span>
          {meta && (
            <span className="tracking-[0.02em] text-tm-muted">{meta}</span>
          )}
        </header>
      )}
      {children !== undefined && children !== null && (
        <div className={clsx("flex flex-col", bodyClassName)}>{children}</div>
      )}
    </section>
  );
}

interface TmCols2Props {
  readonly children: ReactNode;
  readonly className?: string;
}

export function TmCols2({ children, className }: TmCols2Props) {
  return (
    <div
      className={clsx(
        "grid grid-cols-1 bg-tm-bg lg:grid-cols-2",
        // Stacked panes get a horizontal rule. At desktop widths the same
        // relationship becomes one vertical divider.
        "[&>*:not(:last-child)]:border-b [&>*:not(:last-child)]:border-tm-rule lg:[&>*:not(:last-child)]:border-b-0 lg:[&>*:not(:last-child)]:border-r",
        className,
      )}
    >
      {children}
    </div>
  );
}
