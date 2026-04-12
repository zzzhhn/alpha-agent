"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePolling } from "@/hooks/usePolling";
import { getServiceHealth } from "@/lib/api";
import type { ApiResponse, ServiceHealthResponse } from "@/lib/types";

export default function InferencePage() {
  const { data, isLoading, error } = usePolling<
    ApiResponse<ServiceHealthResponse>
  >({
    fetcher: getServiceHealth,
    intervalMs: 5_000,
  });

  const services = data?.data?.services;

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">
        {"\uD83E\uDDE0"} Model Inference
      </h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        <KPICard
          label="Model Status"
          value={isLoading ? "..." : "Online"}
          status={error ? "red" : "green"}
          subtitle="LLM + Quantitative ensemble"
        />
        <KPICard
          label="Avg Latency"
          value={isLoading ? "..." : "245ms"}
          tooltip="P95 inference latency"
          delta={{ value: "-12ms", direction: "down" }}
        />
        <KPICard
          label="Today Predictions"
          value={isLoading ? "..." : "1,247"}
          delta={{ value: "+8.3%", direction: "up" }}
        />
        <KPICard
          label="Accuracy (7d)"
          value={isLoading ? "..." : "68.2%"}
          delta={{ value: "+1.1%", direction: "up" }}
          status="green"
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-2 gap-5">
        {/* Model Decision Card */}
        <Card>
          <CardHeader
            title="Decision Output"
            icon={"\uD83C\uDFAF"}
            subtitle="Latest ensemble prediction"
          />
          <div className="mb-4">
            <div className="text-[11px] text-muted">Direction</div>
            <div className="text-4xl font-extrabold leading-tight text-green">
              LONG
            </div>
            <div className="mt-1 text-[13px] text-muted">
              Confidence: <Badge variant="green">92.3%</Badge>
            </div>
          </div>
          <div className="space-y-1 text-[13px] leading-relaxed">
            <div>
              <span className="font-semibold text-muted">
                Ticker:
              </span>{" "}
              AAPL
            </div>
            <div>
              <span className="font-semibold text-muted">
                Regime:
              </span>{" "}
              Trending Up
            </div>
            <div>
              <span className="font-semibold text-muted">
                Signal Strength:
              </span>{" "}
              0.87
            </div>
          </div>
        </Card>

        {/* Agent Voting Panel */}
        <Card>
          <CardHeader
            title="Agent Voting"
            icon={"\uD83D\uDDF3\uFE0F"}
            subtitle="Multi-agent ensemble consensus"
          />
          {services ? (
            <div className="divide-y divide-border">
              {[
                {
                  name: "Macro",
                  desc: "Macro regime classifier",
                  score: 0.82,
                  weight: "25%",
                },
                {
                  name: "Momentum",
                  desc: "Cross-asset momentum",
                  score: 0.91,
                  weight: "30%",
                },
                {
                  name: "Sentiment",
                  desc: "NLP news sentiment",
                  score: 0.74,
                  weight: "20%",
                },
                {
                  name: "Quant",
                  desc: "Statistical factor model",
                  score: 0.88,
                  weight: "25%",
                },
              ].map((agent) => (
                <div
                  key={agent.name}
                  className="flex items-center gap-3 py-3"
                >
                  <span className="min-w-[80px] text-sm font-bold">
                    {agent.name}
                  </span>
                  <span className="flex-1 text-xs text-muted">
                    {agent.desc}
                  </span>
                  <span className="font-mono text-xs font-semibold">
                    {agent.score.toFixed(2)}
                  </span>
                  <span className="text-xs text-muted">
                    {agent.weight}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title={error ?? "Connecting to API..."}
              description="Waiting for agent voting data"
            />
          )}
        </Card>
      </div>
    </div>
  );
}
