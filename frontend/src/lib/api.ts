import type {
  ApiResponse,
  ServiceHealthResponse,
  PipelineLatency,
  ThroughputMetrics,
  AlphaSignal,
  Position,
  Order,
  AuditEvent,
  MarketIndicators,
  FeatureState,
  AlphaFactor,
  AlphaFactorSummary,
  PortfolioRisk,
  GatewayStatus,
  GateRule,
  AuditSummary,
  SystemConfig,
  BacktestRequest,
  BacktestResult,
  TickerAnalyzeRequest,
  TickerAnalysis,
  TickerSearchResponse,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6008";
const API_PREFIX = `${BASE_URL}/api/v1`;

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly url: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(
  path: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  const url = `${API_PREFIX}${path}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(
        `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        url
      );
    }

    const data = (await response.json()) as T;

    return {
      data,
      error: null,
      timestamp: new Date().toISOString(),
    };
  } catch (error) {
    if (error instanceof ApiError) {
      return {
        data: null,
        error: error.message,
        timestamp: new Date().toISOString(),
      };
    }

    const message =
      error instanceof Error ? error.message : "Unknown error";

    return {
      data: null,
      error: `Network error: ${message}`,
      timestamp: new Date().toISOString(),
    };
  }
}

/* ═══════════════════ API Methods ═══════════════════ */

export function getServiceHealth() {
  return fetchJson<ServiceHealthResponse>("/services/health");
}

export function getServiceHealthById(serviceId: string) {
  return fetchJson<ServiceHealthResponse>(
    `/services/${encodeURIComponent(serviceId)}/health`
  );
}

export function getPipelineLatency() {
  return fetchJson<PipelineLatency>("/pipelines/latency");
}

export function getThroughput() {
  return fetchJson<ThroughputMetrics>("/metrics/throughput");
}

export function getAlphaSignals() {
  return fetchJson<readonly AlphaSignal[]>("/alpha/signals");
}

export function getPositions() {
  return fetchJson<readonly Position[]>("/portfolio/positions");
}

export function getOrders() {
  return fetchJson<readonly Order[]>("/orders");
}

export function getAuditEvents(limit = 50) {
  return fetchJson<readonly AuditEvent[]>(
    `/audit/events?limit=${limit}`
  );
}

export function getAuditEventById(eventId: string) {
  return fetchJson<AuditEvent>(
    `/audit/events/${encodeURIComponent(eventId)}/raw`
  );
}

/* ═══════════════════ Market ═══════════════════ */

export function getMarketIndicators(ticker: string) {
  return fetchJson<MarketIndicators>(
    `/market/indicators/${encodeURIComponent(ticker)}`
  );
}

export function getFeatureState() {
  return fetchJson<FeatureState>("/features/state");
}

/* ═══════════════════ Alpha Factors ═══════════════════ */

export function getAlphaFactors() {
  return fetchJson<readonly AlphaFactor[]>("/alpha/factors");
}

export function getAlphaFactorSummary() {
  return fetchJson<AlphaFactorSummary>("/alpha/factors/summary");
}

/* ═══════════════════ Portfolio ═══════════════════ */

export function getPortfolioRisk() {
  return fetchJson<PortfolioRisk>("/portfolio/risk");
}

/* ═══════════════════ Orders ═══════════════════ */

export function getPendingOrders() {
  return fetchJson<readonly Order[]>("/orders/pending");
}

export function getOrderHistory(limit = 50) {
  return fetchJson<readonly Order[]>(
    `/orders/history?limit=${limit}`
  );
}

/* ═══════════════════ Gateway ═══════════════════ */

export function getGatewayStatus() {
  return fetchJson<GatewayStatus>("/gateway/status");
}

export function getGatewayRules() {
  return fetchJson<readonly GateRule[]>("/gateway/rules");
}

/* ═══════════════════ Audit Decisions ═══════════════════ */

export function getAuditDecisions(limit = 50) {
  return fetchJson<AuditSummary>(
    `/audit/decisions?limit=${limit}`
  );
}

/* ═══════════════════ System ═══════════════════ */

export function getSystemConfig() {
  return fetchJson<SystemConfig>("/system/config");
}

/* ═══════════════════ Interactive (POST) ═══════════════════ */

export function runBacktest(params: BacktestRequest) {
  return fetchJson<BacktestResult>("/backtest/run", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function analyzeTicker(params: TickerAnalyzeRequest) {
  return fetchJson<TickerAnalysis>("/ticker/analyze", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function searchTicker(query: string) {
  return fetchJson<TickerSearchResponse>("/ticker/search", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}
