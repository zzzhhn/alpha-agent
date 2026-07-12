// frontend/src/lib/api/paper.ts
// All calls go through same-origin /api/* so the Next.js middleware injects
// the Authorization Bearer header automatically (see middleware.ts).

export interface PositionOut {
  readonly ticker: string;
  readonly qty: number;
  readonly avg_cost: number;
  readonly current_price: number | null;
  readonly unrealized_pnl: number;
  readonly unrealized_pct: number;
}

export interface AccountResponse {
  readonly account_id: number;
  readonly cash: number;
  readonly initial_cash: number;
  readonly portfolio_value: number;
  readonly total_return_pct: number;
  readonly unrealized_pnl: number;
  readonly realized_pnl: number;
  readonly positions: readonly PositionOut[];
  readonly pending_orders: number;
  readonly reset_count: number;
}

export interface PlaceOrderRequest {
  readonly ticker: string;
  readonly side: "buy" | "sell";
  readonly order_type: "market" | "limit";
  readonly qty: number;
  readonly limit_price?: number;
}

export interface OrderResponse {
  readonly order_id: number;
  readonly status: string;
  readonly signal_date: string;
  readonly message: string;
}

export interface OrderOut {
  readonly id: number;
  readonly ticker: string;
  readonly side: string;
  readonly order_type: string;
  readonly qty: number;
  readonly limit_price: number | null;
  readonly signal_date: string;
  readonly fill_date: string | null;
  readonly fill_price: number | null;
  readonly status: string;
}

export interface OrderListResponse {
  readonly orders: readonly OrderOut[];
  readonly total: number;
}

export interface EquityPoint {
  readonly date: string;
  readonly portfolio_value: number;
  readonly benchmark_index: number;
}

export interface EquityCurveResponse {
  readonly series: readonly EquityPoint[];
  readonly base_date: string | null;
}

export interface ResetResponse {
  readonly reset_count: number;
  readonly cash: number;
  readonly message: string;
}

async function paperFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

export async function fetchPaperAccount(): Promise<AccountResponse> {
  return paperFetch<AccountResponse>("/api/paper/account");
}

export async function placeOrder(req: PlaceOrderRequest): Promise<OrderResponse> {
  return paperFetch<OrderResponse>("/api/paper/order", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function fetchOrders(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<OrderListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const query = qs.toString() ? `?${qs}` : "";
  return paperFetch<OrderListResponse>(`/api/paper/orders${query}`);
}

export async function cancelOrder(orderId: number): Promise<void> {
  const r = await fetch(`/api/paper/order/${orderId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!r.ok && r.status !== 204) {
    const body = await r.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `HTTP ${r.status}`);
  }
}

export async function fetchEquityCurve(): Promise<EquityCurveResponse> {
  return paperFetch<EquityCurveResponse>("/api/paper/equity-curve");
}

export async function resetAccount(): Promise<ResetResponse> {
  return paperFetch<ResetResponse>("/api/paper/reset", { method: "POST" });
}
