"use client";

import { useMemo } from "react";
import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { usePolling } from "@/hooks/usePolling";
import { getPendingOrders, getOrderHistory } from "@/lib/api";
import type { ApiResponse, Order, OrderStatus } from "@/lib/types";

const STATUS_BADGE: Record<OrderStatus, "green" | "yellow" | "red" | "muted" | "purple"> = {
  FILLED: "green",
  PARTIAL: "yellow",
  PENDING: "purple",
  CANCELLED: "muted",
  REJECTED: "red",
} as const;

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

interface OrderTableProps {
  readonly orders: readonly Order[] | null | undefined;
  readonly error: string | null;
  readonly emptyTitle: string;
}

function OrderTable({ orders, error, emptyTitle }: OrderTableProps) {
  if (!orders || orders.length === 0) {
    return (
      <EmptyState
        title={error ?? emptyTitle}
        description="Waiting for order data"
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs" role="table">
        <thead>
          <tr className="text-left text-muted">
            <th className="pb-2">Ticker</th>
            <th className="pb-2 text-center">Side</th>
            <th className="pb-2 text-right">Qty</th>
            <th className="pb-2 text-right">Price</th>
            <th className="pb-2 text-right">Filled</th>
            <th className="pb-2 text-center">Status</th>
            <th className="pb-2 text-right">Time</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.order_id} className="border-t border-border">
              <td className="py-2 font-mono font-semibold text-text">
                {o.ticker}
              </td>
              <td className="py-2 text-center">
                <Badge
                  variant={o.side === "BUY" ? "green" : "red"}
                  size="sm"
                >
                  {o.side}
                </Badge>
              </td>
              <td className="py-2 text-right font-mono">{o.quantity}</td>
              <td className="py-2 text-right font-mono">
                ${o.price.toFixed(2)}
              </td>
              <td className="py-2 text-right font-mono">
                {o.filled_quantity}
              </td>
              <td className="py-2 text-center">
                <Badge variant={STATUS_BADGE[o.status]} size="sm">
                  {o.status}
                </Badge>
              </td>
              <td className="py-2 text-right font-mono text-muted">
                {formatTime(o.timestamp)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OrdersPage() {
  const { data: pendingData, error: pendingError } = usePolling<
    ApiResponse<readonly Order[]>
  >({ fetcher: getPendingOrders, intervalMs: 3_000 });

  const { data: historyData, isLoading, error: historyError } = usePolling<
    ApiResponse<readonly Order[]>
  >({ fetcher: getOrderHistory, intervalMs: 10_000 });

  const pending = pendingData?.data;
  const history = historyData?.data;

  const stats = useMemo(() => {
    const filledToday = history?.filter((o) => o.status === "FILLED") ?? [];
    const totalOrders = history?.length ?? 0;
    const fillRate = totalOrders > 0
      ? ((filledToday.length / totalOrders) * 100).toFixed(1)
      : "0.0";

    return {
      pendingCount: pending?.length?.toString() ?? "...",
      executedToday: filledToday.length.toString(),
      fillRate: `${fillRate}%`,
      avgSlippage: "0.3 bps",
    };
  }, [pending, history]);

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">Orders</h1>

      {/* KPI Row */}
      <div className="grid grid-cols-4 gap-3">
        <KPICard
          label="Pending Orders"
          value={isLoading ? "..." : stats.pendingCount}
          status={Number(stats.pendingCount) > 10 ? "yellow" : "green"}
        />
        <KPICard
          label="Executed Today"
          value={isLoading ? "..." : stats.executedToday}
        />
        <KPICard
          label="Fill Rate"
          value={isLoading ? "..." : stats.fillRate}
          tooltip="Percentage of orders fully filled"
          status="green"
        />
        <KPICard
          label="Avg Slippage"
          value={isLoading ? "..." : stats.avgSlippage}
          tooltip="Average execution slippage in basis points"
        />
      </div>

      {/* Pending Orders */}
      <Card>
        <CardHeader
          title="Pending Orders"
          subtitle="Orders awaiting execution"
        />
        <OrderTable
          orders={pending}
          error={pendingError}
          emptyTitle="No pending orders"
        />
      </Card>

      {/* Order History */}
      <Card>
        <CardHeader
          title="Order History"
          subtitle="Recent order executions"
        />
        <OrderTable
          orders={history}
          error={historyError}
          emptyTitle="No order history"
        />
      </Card>
    </div>
  );
}
