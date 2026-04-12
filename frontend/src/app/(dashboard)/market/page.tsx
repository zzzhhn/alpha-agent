"use client";

import { useState, useMemo, useCallback } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePolling } from "@/hooks/usePolling";
import { getMarketIndicators, getFeatureState } from "@/lib/api";
import type { ApiResponse, MarketIndicators, FeatureState } from "@/lib/types";

const TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"] as const;

function zScoreColor(z: number): string {
  if (z >= 2) return "text-green font-bold";
  if (z >= 1) return "text-green";
  if (z <= -2) return "text-red font-bold";
  if (z <= -1) return "text-red";
  return "text-muted";
}

export default function MarketPage() {
  const [ticker, setTicker] = useState<string>(TICKERS[0]);

  const fetcher = useCallback(
    () => getMarketIndicators(ticker),
    [ticker]
  );

  const { data: indicatorData, isLoading, error } = usePolling<
    ApiResponse<MarketIndicators>
  >({ fetcher, intervalMs: 5_000 });

  const { data: featureData } = usePolling<ApiResponse<FeatureState>>({
    fetcher: getFeatureState,
    intervalMs: 10_000,
  });

  const indicators = indicatorData?.data;
  const features = featureData?.data;

  const handleTickerChange = useCallback((t: string) => {
    setTicker(t);
  }, []);

  const kpiItems = useMemo(() => [
    { label: "RSI", value: indicators?.rsi?.toFixed(1) ?? "...", tooltip: "Relative Strength Index" },
    { label: "MACD", value: indicators?.macd?.toFixed(4) ?? "...", tooltip: "Moving Avg Convergence Divergence" },
    { label: "Bollinger %B", value: indicators?.bollinger_pct_b?.toFixed(2) ?? "...", tooltip: "Bollinger Band %B" },
    { label: "Volatility", value: indicators?.volatility?.toFixed(4) ?? "...", tooltip: "Annualized volatility" },
    { label: "Log Return", value: indicators?.log_return?.toFixed(4) ?? "...", tooltip: "Daily log return" },
  ], [indicators]);

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">Market Data</h1>

      {/* Ticker Selector */}
      <div className="flex gap-1" role="tablist" aria-label="Ticker selector">
        {TICKERS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={t === ticker}
            onClick={() => handleTickerChange(t)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              t === ticker
                ? "bg-accent text-white"
                : "text-muted hover:bg-border hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-5 gap-3">
        {kpiItems.map((kpi) => (
          <KPICard
            key={kpi.label}
            label={kpi.label}
            value={isLoading ? "..." : kpi.value}
            tooltip={kpi.tooltip}
          />
        ))}
      </div>

      <div className="grid grid-cols-2 gap-5">
        {/* Feature Heatmap */}
        <Card>
          <CardHeader
            title="Feature Heatmap"
            subtitle="Z-score: features x tickers"
          />
          {features ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" role="table">
                <thead>
                  <tr>
                    <th className="pb-2 text-left text-muted">Feature</th>
                    {features.tickers.map((t) => (
                      <th key={t} className="pb-2 text-center text-muted">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {features.features.map((feat, ri) => (
                    <tr key={feat} className="border-t border-border">
                      <td className="py-1.5 font-mono text-text">{feat}</td>
                      {features.heatmap[ri]?.map((z, ci) => (
                        <td
                          key={`${feat}-${features.tickers[ci]}`}
                          className={`py-1.5 text-center font-mono ${zScoreColor(z)}`}
                        >
                          {z.toFixed(2)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={error ?? "Loading feature data..."}
              description="Waiting for feature state"
            />
          )}
        </Card>

        {/* Candlestick Chart Placeholder */}
        <Card>
          <CardHeader
            title="Price Chart"
            subtitle={`${ticker} candlestick`}
          />
          <div
            className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border"
            role="img"
            aria-label="Candlestick chart placeholder"
          >
            <span className="text-sm text-muted">
              TradingView chart loading...
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
}
