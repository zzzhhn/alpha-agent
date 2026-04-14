"use client";

import { useState, useCallback, useMemo } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { useAuditDecisions, useOrderHistory } from "@/hooks/useDashboard";
import type { AuditDecision, Order } from "@/lib/types";

/* ── Fallback data ──────────────────────────────────────────────── */

const FALLBACK_DECISIONS: readonly AuditDecision[] = [
  { id: "d_001", timestamp: "2025-04-12T14:30:15Z", ticker: "AAPL", direction: "LONG", confidence: 92.3, reasoning: "Strong momentum + positive sentiment", reasoning_chain: ["Macro: Bull regime (72%)", "Momentum: RSI 62, uptrend confirmed", "Sentiment: NLP score +0.74", "Quant: Factor composite 0.88"], accepted: true },
  { id: "d_002", timestamp: "2025-04-12T14:15:42Z", ticker: "NVDA", direction: "LONG", confidence: 85.1, reasoning: "Sector rotation into tech + earnings catalyst", reasoning_chain: ["Macro: Risk-on environment", "Momentum: Breaking out of consolidation", "Sentiment: Analyst upgrades +3"], accepted: true },
  { id: "d_003", timestamp: "2025-04-12T13:45:10Z", ticker: "TSLA", direction: "SHORT", confidence: 67.8, reasoning: "Overextended rally + negative news flow", reasoning_chain: ["Macro: Mixed signals", "Momentum: RSI 78, overbought", "Sentiment: NLP score -0.31"], accepted: false },
];

const FALLBACK_ORDERS: readonly Order[] = [
  { order_id: "o_001", ticker: "AAPL", side: "BUY", quantity: 100, price: 178.50, status: "FILLED", filled_quantity: 100, timestamp: "2025-04-12T14:31:02Z" },
  { order_id: "o_002", ticker: "NVDA", side: "BUY", quantity: 50, price: 875.20, status: "FILLED", filled_quantity: 50, timestamp: "2025-04-12T14:16:15Z" },
  { order_id: "o_003", ticker: "TSLA", side: "SELL", quantity: 30, price: 245.80, status: "CANCELLED", filled_quantity: 0, timestamp: "2025-04-12T13:46:00Z" },
];

/* ── Helpers ─────────────────────────────────────────────────────── */

type Tab = "decisions" | "executions";

function directionVariant(dir: string) {
  if (dir === "LONG") return "green" as const;
  if (dir === "SHORT") return "red" as const;
  return "muted" as const;
}

function statusVariant(s: string) {
  if (s === "FILLED") return "green" as const;
  if (s === "CANCELLED" || s === "REJECTED") return "red" as const;
  if (s === "PARTIAL") return "yellow" as const;
  return "muted" as const;
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return iso;
  }
}

/* ── Page ────────────────────────────────────────────────────────── */

export default function ActivityPage() {
  const { locale } = useLocale();
  const { data: auditData } = useAuditDecisions();
  const { data: orderData } = useOrderHistory();

  const [tab, setTab] = useState<Tab>("decisions");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const decisions = auditData?.data?.decisions ?? FALLBACK_DECISIONS;
  const orders = (orderData?.data as readonly Order[] | undefined) ?? FALLBACK_ORDERS;

  const filteredDecisions = useMemo(() => {
    if (!filter) return decisions;
    const lower = filter.toLowerCase();
    return decisions.filter(
      (d) =>
        d.ticker.toLowerCase().includes(lower) ||
        d.direction.toLowerCase().includes(lower) ||
        d.reasoning.toLowerCase().includes(lower)
    );
  }, [decisions, filter]);

  const filteredOrders = useMemo(() => {
    if (!filter) return orders;
    const lower = filter.toLowerCase();
    return orders.filter(
      (o) =>
        o.ticker.toLowerCase().includes(lower) ||
        o.side.toLowerCase().includes(lower) ||
        o.status.toLowerCase().includes(lower)
    );
  }, [orders, filter]);

  const handleToggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-semibold text-[var(--text)]">
        📋 {t(locale, "activity.title")}
      </h1>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg border border-[var(--border)] bg-[var(--glass-bg)] p-1">
        {(["decisions", "executions"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-md px-4 py-2 text-xs font-medium transition-colors ${
              tab === key
                ? "bg-[var(--accent)] text-white"
                : "text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            {t(locale, `activity.${key}` as Parameters<typeof t>[1])}
          </button>
        ))}
      </div>

      {/* Filter */}
      <input
        type="text"
        placeholder={t(locale, "activity.filter")}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="w-64 rounded-md border border-[var(--border)] bg-transparent px-3 py-1.5 text-xs text-[var(--text)] placeholder:text-[var(--muted)] focus:border-[var(--accent)] focus:outline-none"
      />

      {/* Decisions tab */}
      {tab === "decisions" && (
        <Card>
          <CardHeader
            title={t(locale, "activity.decisions")}
            icon="📊"
            subtitle={`${filteredDecisions.length} records`}
          />
          {filteredDecisions.length === 0 ? (
            <EmptyState title={t(locale, "activity.noData")} />
          ) : (
            <div className="overflow-hidden rounded-lg border border-[var(--border)]">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--glass-bg)]">
                    {["Time", "Ticker", "Direction", "Confidence", "Reasoning", "Status"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-[var(--muted)]">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {filteredDecisions.map((d) => (
                    <tr key={d.id} className="group">
                      <td colSpan={6} className="p-0">
                        <button
                          type="button"
                          onClick={() => handleToggle(d.id)}
                          className="flex w-full items-center hover:bg-[rgba(255,255,255,0.02)] focus:outline-none"
                          aria-expanded={expandedId === d.id}
                        >
                          <span className="w-[14%] px-3 py-2 text-left font-mono-data text-[var(--muted)]">
                            {formatTime(d.timestamp)}
                          </span>
                          <span className="w-[12%] px-3 py-2 text-left font-mono-data font-bold text-[var(--text)]">
                            {d.ticker}
                          </span>
                          <span className="w-[14%] px-3 py-2 text-left">
                            <Badge variant={directionVariant(d.direction)} size="sm">{d.direction}</Badge>
                          </span>
                          <span className="w-[14%] px-3 py-2 text-left font-mono-data">
                            {d.confidence.toFixed(1)}%
                          </span>
                          <span className="w-[32%] truncate px-3 py-2 text-left text-[var(--muted)]">
                            {d.reasoning}
                          </span>
                          <span className="w-[14%] px-3 py-2 text-left">
                            <Badge variant={d.accepted ? "green" : "red"} size="sm">
                              {d.accepted ? "Accepted" : "Rejected"}
                            </Badge>
                          </span>
                        </button>
                        {expandedId === d.id && (
                          <div className="border-t border-[var(--border)] bg-[var(--glass-bg)] px-6 py-3">
                            <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--muted)]">
                              {t(locale, "activity.reasoning")}
                            </div>
                            <ol className="list-decimal list-inside space-y-1 text-xs text-[var(--text-secondary)]">
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
      )}

      {/* Executions tab */}
      {tab === "executions" && (
        <Card>
          <CardHeader
            title={t(locale, "activity.executions")}
            icon="⚡"
            subtitle={`${filteredOrders.length} orders`}
          />
          {filteredOrders.length === 0 ? (
            <EmptyState title={t(locale, "activity.noData")} />
          ) : (
            <div className="overflow-hidden rounded-lg border border-[var(--border)]">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--glass-bg)]">
                    {["Time", "Order ID", "Ticker", "Side", "Qty", "Price", "Filled", "Status"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-[var(--muted)]">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {filteredOrders.map((o) => (
                    <tr key={o.order_id} className="hover:bg-[rgba(255,255,255,0.02)]">
                      <td className="px-3 py-2 font-mono-data text-[var(--muted)]">{formatTime(o.timestamp)}</td>
                      <td className="px-3 py-2 font-mono-data text-[var(--muted)]">{o.order_id}</td>
                      <td className="px-3 py-2 font-mono-data font-bold text-[var(--text)]">{o.ticker}</td>
                      <td className="px-3 py-2">
                        <Badge variant={o.side === "BUY" ? "green" : "red"} size="sm">{o.side}</Badge>
                      </td>
                      <td className="px-3 py-2 font-mono-data">{o.quantity}</td>
                      <td className="px-3 py-2 font-mono-data">${o.price.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono-data">{o.filled_quantity}</td>
                      <td className="px-3 py-2">
                        <Badge variant={statusVariant(o.status)} size="sm">{o.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
