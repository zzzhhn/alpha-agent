"use client";

import { useState, useCallback, useMemo } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useAuditDecisions } from "@/hooks/useDashboard";
import type { AuditDecision } from "@/lib/types";

const FALLBACK_DECISIONS: readonly AuditDecision[] = [
  { id: "d_001", timestamp: "2025-04-12T14:30:15Z", ticker: "AAPL", direction: "LONG", confidence: 92.3, reasoning: "Strong momentum + positive sentiment", reasoning_chain: ["Macro: Bull regime (72%)", "Momentum: RSI 62, uptrend confirmed", "Sentiment: NLP score +0.74", "Quant: Factor composite 0.88"], accepted: true },
  { id: "d_002", timestamp: "2025-04-12T14:15:42Z", ticker: "NVDA", direction: "LONG", confidence: 85.1, reasoning: "Sector rotation into tech + earnings catalyst", reasoning_chain: ["Macro: Risk-on environment", "Momentum: Breaking out of consolidation", "Sentiment: Analyst upgrades +3"], accepted: true },
  { id: "d_003", timestamp: "2025-04-12T13:45:10Z", ticker: "TSLA", direction: "SHORT", confidence: 67.8, reasoning: "Overextended rally + negative news flow", reasoning_chain: ["Macro: Mixed signals", "Momentum: RSI 78, overbought", "Sentiment: NLP score -0.31"], accepted: false },
  { id: "d_004", timestamp: "2025-04-12T12:30:05Z", ticker: "MSFT", direction: "NEUTRAL", confidence: 51.2, reasoning: "Conflicting signals, no clear edge", reasoning_chain: ["Macro: Neutral", "Momentum: Sideways channel", "Sentiment: Mixed"], accepted: false },
] as const;

function directionVariant(dir: string) {
  if (dir === "LONG") return "green" as const;
  if (dir === "SHORT") return "red" as const;
  return "muted" as const;
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return iso;
  }
}

export default function AuditPage() {
  const { data, isLoading, error } = useAuditDecisions();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const summary = data?.data;
  const decisions = summary?.decisions ?? FALLBACK_DECISIONS;

  const filtered = useMemo(() => {
    if (!filter) return decisions;
    const lower = filter.toLowerCase();
    return decisions.filter(
      (d) =>
        d.ticker.toLowerCase().includes(lower) ||
        d.direction.toLowerCase().includes(lower) ||
        d.reasoning.toLowerCase().includes(lower)
    );
  }, [decisions, filter]);

  const totalDecisions = summary?.total_decisions ?? decisions.length;
  const acceptanceRate = summary?.acceptance_rate ??
    (decisions.filter((d) => d.accepted).length / Math.max(decisions.length, 1)) * 100;
  const avgConfidence = summary?.avg_confidence ??
    decisions.reduce((sum, d) => sum + d.confidence, 0) / Math.max(decisions.length, 1);
  const lastTime = summary?.last_decision_time ?? decisions[0]?.timestamp ?? "-";

  const handleToggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  const handleFilterChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setFilter(e.target.value);
    },
    []
  );

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">
        {"\uD83D\uDCDC"} Audit Trail
      </h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        <KPICard
          label="Total Decisions"
          value={isLoading ? "..." : String(totalDecisions)}
        />
        <KPICard
          label="Acceptance Rate"
          value={isLoading ? "..." : `${acceptanceRate.toFixed(1)}%`}
          status={acceptanceRate >= 70 ? "green" : "yellow"}
        />
        <KPICard
          label="Avg Confidence"
          value={isLoading ? "..." : `${avgConfidence.toFixed(1)}%`}
        />
        <KPICard
          label="Last Decision"
          value={isLoading ? "..." : formatTime(lastTime)}
          subtitle="Most recent timestamp"
        />
      </div>

      {/* Decision Timeline */}
      <Card>
        <CardHeader
          title="Decision Timeline"
          icon={"\uD83D\uDCCB"}
          subtitle="Click a row to expand reasoning chain"
          actions={
            <input
              type="text"
              placeholder="Filter by ticker, direction..."
              value={filter}
              onChange={handleFilterChange}
              className="w-56 rounded-md border border-border bg-transparent px-3 py-1 text-xs text-text placeholder:text-muted focus:border-accent focus:outline-none"
              aria-label="Filter decisions"
            />
          }
        />
        {error && !summary ? (
          <EmptyState title="Connection Error" description={error} />
        ) : filtered.length === 0 ? (
          <EmptyState title="No matches" description="Try adjusting your filter" />
        ) : (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-xs" role="table">
              <thead>
                <tr className="border-b border-border">
                  {["Time", "Ticker", "Direction", "Confidence", "Reasoning", "Status"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((d) => (
                  <tr key={d.id} className="group">
                    <td colSpan={6} className="p-0">
                      <button
                        type="button"
                        onClick={() => handleToggle(d.id)}
                        className="flex w-full items-center hover:bg-white/[0.02] focus:outline-none"
                        aria-expanded={expandedId === d.id}
                      >
                        <span className="w-[14%] px-3 py-2 text-left font-mono text-muted">
                          {formatTime(d.timestamp)}
                        </span>
                        <span className="w-[12%] px-3 py-2 text-left font-mono font-bold text-text">
                          {d.ticker}
                        </span>
                        <span className="w-[14%] px-3 py-2 text-left">
                          <Badge variant={directionVariant(d.direction)} size="sm">
                            {d.direction}
                          </Badge>
                        </span>
                        <span className="w-[14%] px-3 py-2 text-left font-mono">
                          {d.confidence.toFixed(1)}%
                        </span>
                        <span className="w-[32%] truncate px-3 py-2 text-left text-muted">
                          {d.reasoning}
                        </span>
                        <span className="w-[14%] px-3 py-2 text-left">
                          <Badge variant={d.accepted ? "green" : "red"} size="sm">
                            {d.accepted ? "Accepted" : "Rejected"}
                          </Badge>
                        </span>
                      </button>
                      {expandedId === d.id && (
                        <div className="border-t border-border bg-white/[0.01] px-6 py-3">
                          <div className="text-[11px] font-semibold text-muted mb-1">
                            Reasoning Chain
                          </div>
                          <ol className="list-decimal list-inside space-y-1 text-xs text-text">
                            {d.reasoning_chain.map((step, i) => (
                              <li key={i}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
