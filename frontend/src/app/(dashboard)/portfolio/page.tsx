"use client";

import { useMemo } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePolling } from "@/hooks/usePolling";
import { getPositions, getPortfolioRisk } from "@/lib/api";
import type { ApiResponse, Position, PortfolioRisk } from "@/lib/types";

function pnlColor(value: number): string {
  if (value > 0) return "text-green";
  if (value < 0) return "text-red";
  return "text-muted";
}

function directionLabel(weight: number): string {
  if (weight > 0) return "LONG";
  if (weight < 0) return "SHORT";
  return "FLAT";
}

export default function PortfolioPage() {
  const { data: posData, error: posError } = usePolling<
    ApiResponse<readonly Position[]>
  >({ fetcher: getPositions, intervalMs: 5_000 });

  const { data: riskData, isLoading } = usePolling<
    ApiResponse<PortfolioRisk>
  >({ fetcher: getPortfolioRisk, intervalMs: 10_000 });

  const positions = posData?.data;
  const risk = riskData?.data;

  const kpiItems = useMemo(() => [
    {
      label: "Total Exposure",
      value: risk ? `${(risk.total_exposure * 100).toFixed(1)}%` : "...",
    },
    {
      label: "Diversification",
      value: risk?.diversification_score?.toFixed(2) ?? "...",
      tooltip: "Portfolio diversification score (0-1)",
    },
    {
      label: "Max Position",
      value: risk ? `${(risk.max_position_pct * 100).toFixed(1)}%` : "...",
      status: (risk && risk.max_position_pct > 0.2 ? "red" : "green") as "red" | "green",
    },
    {
      label: "VaR 95%",
      value: risk?.var_95?.toFixed(2) ?? "...",
      tooltip: "Value at Risk (95th percentile)",
      status: "yellow" as const,
    },
  ], [risk]);

  const riskMetrics = useMemo(() => {
    if (!risk) return [];
    return [
      { label: "Sharpe Ratio", value: risk.sharpe_ratio.toFixed(2) },
      { label: "Max Drawdown", value: `${(risk.max_drawdown * 100).toFixed(1)}%` },
      { label: "Beta", value: risk.beta.toFixed(2) },
      { label: "VaR 95%", value: risk.var_95.toFixed(2) },
    ];
  }, [risk]);

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">Portfolio</h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        {kpiItems.map((kpi) => (
          <KPICard
            key={kpi.label}
            label={kpi.label}
            value={isLoading ? "..." : kpi.value}
            tooltip={kpi.tooltip}
            status={kpi.status}
          />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Positions Table */}
        <Card className="col-span-2">
          <CardHeader
            title="Positions"
            subtitle="Current portfolio holdings"
          />
          {positions && positions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" role="table">
                <thead>
                  <tr className="text-left text-muted">
                    <th className="pb-2">Ticker</th>
                    <th className="pb-2 text-center">Direction</th>
                    <th className="pb-2 text-right">Weight</th>
                    <th className="pb-2 text-right">Qty</th>
                    <th className="pb-2 text-right">Avg Price</th>
                    <th className="pb-2 text-right">Current</th>
                    <th className="pb-2 text-right">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.ticker} className="border-t border-border">
                      <td className="py-2 font-mono font-semibold text-text">
                        {p.ticker}
                      </td>
                      <td className="py-2 text-center">
                        <Badge
                          variant={p.weight >= 0 ? "green" : "red"}
                          size="sm"
                        >
                          {directionLabel(p.weight)}
                        </Badge>
                      </td>
                      <td className="py-2 text-right font-mono">
                        {(p.weight * 100).toFixed(1)}%
                      </td>
                      <td className="py-2 text-right font-mono">{p.quantity}</td>
                      <td className="py-2 text-right font-mono">
                        ${p.avg_price.toFixed(2)}
                      </td>
                      <td className="py-2 text-right font-mono">
                        ${p.current_price.toFixed(2)}
                      </td>
                      <td className={`py-2 text-right font-mono ${pnlColor(p.pnl)}`}>
                        {p.pnl >= 0 ? "+" : ""}{p.pnl.toFixed(2)} ({p.pnl_pct.toFixed(1)}%)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={posError ?? "No positions"}
              description="Waiting for portfolio data"
            />
          )}
        </Card>

        {/* Risk Metrics Card */}
        <Card>
          <CardHeader
            title="Risk Metrics"
            subtitle="Portfolio risk summary"
          />
          {riskMetrics.length > 0 ? (
            <div className="space-y-3">
              {riskMetrics.map((m) => (
                <div key={m.label} className="flex items-center justify-between">
                  <span className="text-xs text-muted">{m.label}</span>
                  <span className="font-mono text-sm font-semibold text-text">
                    {m.value}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Loading risk metrics..."
              description="Calculating portfolio risk"
            />
          )}
        </Card>
      </div>
    </div>
  );
}
