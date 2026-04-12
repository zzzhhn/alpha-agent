"use client";

import { useMemo } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePolling } from "@/hooks/usePolling";
import { getAlphaFactors, getAlphaFactorSummary } from "@/lib/api";
import type {
  ApiResponse,
  AlphaFactor,
  AlphaFactorSummary,
  FactorStatus,
} from "@/lib/types";

const STATUS_BADGE: Record<FactorStatus, "green" | "yellow" | "muted"> = {
  active: "green",
  testing: "yellow",
  disabled: "muted",
} as const;

export default function AlphaPage() {
  const { data: factorsData, error: factorsError } = usePolling<
    ApiResponse<readonly AlphaFactor[]>
  >({ fetcher: getAlphaFactors, intervalMs: 10_000 });

  const { data: summaryData, isLoading } = usePolling<
    ApiResponse<AlphaFactorSummary>
  >({ fetcher: getAlphaFactorSummary, intervalMs: 10_000 });

  const factors = factorsData?.data;
  const summary = summaryData?.data;

  const kpiItems = useMemo(() => [
    { label: "Best IC", value: summary?.best_ic?.toFixed(4) ?? "...", status: "green" as const },
    { label: "Best Sharpe", value: summary?.best_sharpe?.toFixed(2) ?? "..." },
    { label: "Total Factors", value: summary?.total_factors?.toString() ?? "..." },
    {
      label: "Pipeline Status",
      value: summary?.pipeline_status ?? "...",
      status: (summary?.pipeline_status === "running" ? "green" : "yellow") as "green" | "yellow",
    },
  ], [summary]);

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">Alpha Factors</h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        {kpiItems.map((kpi) => (
          <KPICard
            key={kpi.label}
            label={kpi.label}
            value={isLoading ? "..." : kpi.value}
            status={kpi.status}
          />
        ))}
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Factor Table */}
        <Card className="col-span-2">
          <CardHeader
            title="Factor Library"
            subtitle="All discovered alpha factors"
          />
          {factors && factors.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" role="table">
                <thead>
                  <tr className="text-left text-muted">
                    <th className="pb-2">Expression</th>
                    <th className="pb-2 text-right">IC</th>
                    <th className="pb-2 text-right">ICIR</th>
                    <th className="pb-2 text-right">Sharpe</th>
                    <th className="pb-2 text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {factors.map((f) => (
                    <tr key={f.id} className="border-t border-border">
                      <td className="max-w-[240px] truncate py-2 font-mono text-text">
                        {f.expression}
                      </td>
                      <td className="py-2 text-right font-mono">{f.ic.toFixed(4)}</td>
                      <td className="py-2 text-right font-mono">{f.icir.toFixed(2)}</td>
                      <td className="py-2 text-right font-mono">{f.sharpe.toFixed(2)}</td>
                      <td className="py-2 text-center">
                        <Badge variant={STATUS_BADGE[f.status]} size="sm">
                          {f.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={factorsError ?? "No factors found"}
              description="Waiting for alpha factor data"
            />
          )}
        </Card>

        {/* Factor DSL Editor Placeholder */}
        <Card>
          <CardHeader
            title="Factor Editor"
            subtitle="DSL expression builder"
          />
          <div
            className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border"
            role="textbox"
            aria-label="Factor DSL editor placeholder"
          >
            <span className="text-sm text-muted">
              Monaco editor slot
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
}
