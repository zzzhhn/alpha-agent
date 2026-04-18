"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { EquityCurve } from "@/components/charts/EquityCurve";
import { Badge } from "@/components/ui/Badge";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { BacktestResult } from "@/lib/types";

interface BacktestResultsProps {
  readonly result: BacktestResult;
  readonly isFavorite?: boolean;
  readonly onToggleFavorite?: () => void;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

function formatNum(v: number): string {
  return v.toFixed(4);
}

export function BacktestResults({
  result,
  isFavorite = false,
  onToggleFavorite,
}: BacktestResultsProps) {
  const { locale } = useLocale();
  const m = result.metrics;
  const isProfit = m.total_return > 0;

  return (
    <div className="space-y-4">
      {/* Result Header with Favorite Toggle */}
      {onToggleFavorite && (
        <div className="flex items-center justify-between px-1">
          <div className="font-mono text-[11px] text-muted">
            {result.ticker} | {result.start_date} &rarr; {result.end_date}
          </div>
          <button
            type="button"
            onClick={onToggleFavorite}
            title={t(
              locale,
              isFavorite ? "backtest.unfavoriteAction" : "backtest.favoriteAction"
            )}
            aria-pressed={isFavorite}
            className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${
              isFavorite
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-[var(--toggle-bg)] text-muted hover:border-accent/50 hover:text-text"
            }`}
          >
            <span>{isFavorite ? "\u2605" : "\u2606"}</span>
            <span>
              {t(
                locale,
                isFavorite ? "backtest.unfavorite" : "backtest.favorite"
              )}
            </span>
          </button>
        </div>
      )}

      {/* KPI Row */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KPICard
          label={t(locale, "backtest.totalReturn")}
          value={formatPct(m.total_return)}
          status={isProfit ? "green" : "red"}
          delta={{
            value: `$${(m.final_value - 100000).toLocaleString()}`,
            direction: isProfit ? "up" : "down",
          }}
          tooltip={locale === "zh"
            ? "策略总收益率（初始资金$100,000）"
            : "Total return from initial $100,000 capital"
          }
        />
        <KPICard
          label={t(locale, "backtest.sharpe")}
          value={formatNum(m.sharpe_ratio)}
          status={m.sharpe_ratio > 1 ? "green" : m.sharpe_ratio > 0 ? "yellow" : "red"}
          tooltip={locale === "zh"
            ? "年化夏普比率 = 收益/风险，>1为优秀"
            : "Annualized Sharpe = return/risk, >1 is excellent"
          }
        />
        <KPICard
          label={t(locale, "backtest.maxDrawdown")}
          value={formatPct(m.max_drawdown)}
          status={m.max_drawdown > -0.1 ? "green" : m.max_drawdown > -0.2 ? "yellow" : "red"}
          tooltip={locale === "zh"
            ? "最大峰谷回撤，衡量最坏情况下的损失"
            : "Maximum peak-to-trough decline, measures worst-case loss"
          }
        />
        <KPICard
          label={t(locale, "backtest.winRate")}
          value={formatPct(m.win_rate)}
          subtitle={`${m.total_trades} ${locale === "zh" ? "笔交易" : "trades"}`}
          status={m.win_rate > 0.5 ? "green" : "yellow"}
          tooltip={locale === "zh"
            ? "盈利交易占总交易的比例"
            : "Percentage of profitable trades"
          }
        />
      </div>

      {/* Equity Curve */}
      <Card>
        <CardHeader
          title={t(locale, "backtest.equityCurve")}
          icon="\uD83D\uDCC8"
          subtitle={`${result.ticker} | ${result.start_date} \u2192 ${result.end_date}`}
        />
        <div className="p-4">
          <EquityCurve data={result.equity_curve} />
        </div>
      </Card>

      {/* Trade History */}
      {result.trades.length > 0 && (
        <Card>
          <CardHeader
            title={t(locale, "backtest.trades")}
            icon="⚡"
            subtitle={`${result.trades.length} ${locale === "zh" ? "条记录" : "records"}`}
          />
          <div className="overflow-x-auto p-4">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] text-muted">
                  <th className="pb-2 pr-4">{locale === "zh" ? "日期" : "Date"}</th>
                  <th className="pb-2 pr-4">{locale === "zh" ? "方向" : "Side"}</th>
                  <th className="pb-2 pr-4 text-right">{locale === "zh" ? "价格" : "Price"}</th>
                  <th className="pb-2 pr-4 text-right">{locale === "zh" ? "数量" : "Shares"}</th>
                  <th className="pb-2 text-right">{locale === "zh" ? "盈亏" : "P&L"}</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade, i) => (
                  <tr key={`${trade.date}-${i}`} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-xs text-muted">
                      {trade.date}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge
                        variant={trade.side.startsWith("BUY") ? "green" : "red"}
                        size="sm"
                      >
                        {trade.side}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-xs text-text">
                      ${trade.price.toFixed(2)}
                    </td>
                    <td className="py-2 pr-4 text-right font-mono text-xs text-text">
                      {trade.shares}
                    </td>
                    <td className="py-2 text-right font-mono text-xs font-semibold"
                      style={{ color: trade.pnl >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {trade.pnl !== 0
                        ? `${trade.pnl >= 0 ? "+" : ""}$${trade.pnl.toFixed(2)}`
                        : "\u2014"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
