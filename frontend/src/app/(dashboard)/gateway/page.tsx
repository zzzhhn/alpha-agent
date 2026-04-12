"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useGatewayStatus } from "@/hooks/useDashboard";
import type { GateRule } from "@/lib/types";

const FALLBACK_RULES: readonly GateRule[] = [
  { name: "Drawdown Limit", enabled: true, passed: true, confidence: 95, reason: "Current drawdown 2.1% < 5% limit" },
  { name: "Concentration Check", enabled: true, passed: true, confidence: 88, reason: "Max position weight 12% < 20% cap" },
  { name: "Volatility Filter", enabled: true, passed: false, confidence: 42, reason: "VIX at 28.5, above 25 threshold" },
  { name: "Liquidity Gate", enabled: true, passed: true, confidence: 91, reason: "ADV ratio 0.3% within limits" },
  { name: "Correlation Check", enabled: false, passed: true, confidence: 0, reason: "Rule disabled" },
  { name: "Regime Filter", enabled: true, passed: true, confidence: 76, reason: "Bull regime probability 72%" },
] as const;

function confidenceVariant(pct: number) {
  if (pct >= 80) return "green" as const;
  if (pct >= 50) return "yellow" as const;
  return "red" as const;
}

export default function GatewayPage() {
  const { data, isLoading, error } = useGatewayStatus();
  const gateway = data?.data;
  const rules = gateway?.rules ?? FALLBACK_RULES;

  const passed = gateway?.gates_passed ?? rules.filter((r) => r.passed).length;
  const failed = gateway?.gates_failed ?? rules.filter((r) => !r.passed && r.enabled).length;
  const confidence = gateway?.overall_confidence ?? 78.4;
  const description = gateway?.signal_description ?? "Conditional LONG - 1 gate blocked";

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">
        {"\uD83D\uDEE1\uFE0F"} Risk Gate
      </h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        <KPICard
          label="Gates Passed"
          value={isLoading ? "..." : String(passed)}
          status="green"
        />
        <KPICard
          label="Gates Failed"
          value={isLoading ? "..." : String(failed)}
          status={failed > 0 ? "red" : "green"}
        />
        <KPICard
          label="Overall Confidence"
          value={isLoading ? "..." : `${confidence.toFixed(1)}%`}
          status={confidenceVariant(confidence)}
        />
        <KPICard
          label="Signal"
          value={isLoading ? "..." : description}
          subtitle="Current ensemble output"
        />
      </div>

      {/* Gate Rules Table */}
      <Card>
        <CardHeader
          title="Gate Evaluation"
          icon={"\u2699\uFE0F"}
          subtitle="Real-time rule pass/fail status"
        />
        {error && !gateway ? (
          <EmptyState title="Connection Error" description={error} />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-xs" role="table">
              <thead>
                <tr className="border-b border-border">
                  {["Rule", "Status", "Confidence", "Reason"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-muted">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rules.filter((r) => r.enabled).map((rule) => (
                  <tr key={rule.name} className="hover:bg-white/[0.02]">
                    <td className="px-3 py-2 font-semibold text-text">{rule.name}</td>
                    <td className="px-3 py-2">
                      <Badge variant={rule.passed ? "green" : "red"} size="sm">
                        {rule.passed ? "\u2713 Pass" : "\u2717 Fail"}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 font-mono">
                      <Badge variant={confidenceVariant(rule.confidence)} size="sm">
                        {rule.confidence}%
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-muted">{rule.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Gate Rules Config */}
      <Card>
        <CardHeader
          title="Rule Configuration"
          icon={"\uD83D\uDCCB"}
          subtitle="All registered gate rules"
        />
        <div className="flex flex-wrap gap-2">
          {rules.map((rule) => (
            <Badge
              key={rule.name}
              variant={rule.enabled ? "green" : "muted"}
              size="md"
            >
              {rule.name}: {rule.enabled ? "ON" : "OFF"}
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}
