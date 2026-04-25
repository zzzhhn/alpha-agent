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
  FactorAnalysisResult,
  GateSimulationResult,
  StressTestResult,
  HypothesisTranslateRequest,
  HypothesisTranslateResponse,
  FactorBacktestRequest,
  FactorBacktestResponse,
  UniverseListResponse,
  OperandCatalogResponse,
  CoverageResponse,
  SignalSpec,
  SignalTodayResponse,
  ICTimeseriesResponse,
  ExposureResponse,
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

// Vercel's anycast edge pool occasionally serves a dead node — symptom is
// `TypeError: Failed to fetch` because the TLS handshake gets reset and the
// browser surfaces a network error. A single retry against a fresh connection
// usually lands on a healthy node and recovers the request transparently.
// See feedback_vercel_edge_ip_poisoning.md.
const MAX_RETRIES = 1;
const RETRY_DELAY_MS = 600;

async function _doFetch<T>(url: string, options?: RequestInit): Promise<T> {
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
      url,
    );
  }
  return (await response.json()) as T;
}

async function fetchJson<T>(
  path: string,
  options?: RequestInit
): Promise<ApiResponse<T>> {
  const url = `${API_PREFIX}${path}`;
  let lastError: unknown;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const data = await _doFetch<T>(url, options);
      return { data, error: null, timestamp: new Date().toISOString() };
    } catch (error) {
      lastError = error;
      // Only retry on transient network errors (TypeError) or 5xx upstreams.
      const transient =
        error instanceof TypeError ||
        (error instanceof ApiError && error.status >= 500);
      if (transient && attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        continue;
      }
      break;
    }
  }

  const timestamp = new Date().toISOString();
  if (lastError instanceof ApiError) {
    return { data: null, error: lastError.message, timestamp };
  }
  if (lastError instanceof SyntaxError) {
    return {
      data: null,
      error: `Invalid JSON response (backend likely offline or returning HTML): ${lastError.message}`,
      timestamp,
    };
  }
  if (lastError instanceof TypeError) {
    return {
      data: null,
      error: `Network unreachable after retry (likely Vercel edge node poisoning — try Cmd+Shift+R or flush DNS cache): ${lastError.message}`,
      timestamp,
    };
  }
  const message = lastError instanceof Error ? lastError.message : "Unknown error";
  return { data: null, error: `Unknown error: ${message}`, timestamp };
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

/* ── Phase 2: Factor Analytics + Gate Editor ── */

export function analyzeFactors(ticker: string, sortBy = "ic") {
  return fetchJson<FactorAnalysisResult>("/factors/analyze", {
    method: "POST",
    body: JSON.stringify({ ticker, sort_by: sortBy }),
  });
}

export function simulateGates(params: {
  ticker: string;
  gate_threshold?: number;
  weight_trend?: number;
  weight_momentum?: number;
  weight_entry?: number;
}) {
  return fetchJson<GateSimulationResult>("/gates/simulate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/* ── Phase 3: Portfolio Stress Test ── */

export function runStressTest(params: {
  positions: { ticker: string; value: number }[];
  scenario?: string;
  custom_shocks?: Record<string, number>;
}) {
  return fetchJson<StressTestResult>("/portfolio/stress", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/* ── W2: Hypothesis Translator (T1) ── */

export function translateHypothesis(params: HypothesisTranslateRequest) {
  return fetchJson<HypothesisTranslateResponse>("/alpha/translate", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function runFactorBacktest(params: FactorBacktestRequest) {
  return fetchJson<FactorBacktestResponse>("/factor/backtest", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/* ── P1: Data layer (introspection, GET-only) ── */
//
// Module-level promise cache for the three Data endpoints. The /data page
// re-mounts on every navigation (Next.js App Router doesn't preserve client
// component state across route changes), so without caching the user pays
// 3 network round-trips every time they revisit. Since the panel is static
// (refreshed only when the parquet is rebuilt + redeployed), an in-memory
// cache that survives the page lifecycle but resets on full reload is the
// right fit.
//
// Failure handling: if the first request errors, the cached promise is
// cleared so the next caller retries. Successful cache lives until tab close
// or explicit `force: true`.

interface CacheOpts {
  readonly force?: boolean;
}

let _universeCache: Promise<ApiResponse<UniverseListResponse>> | null = null;
let _catalogCache: Promise<ApiResponse<OperandCatalogResponse>> | null = null;
const _coverageCache = new Map<string, Promise<ApiResponse<CoverageResponse>>>();

function _wrapCache<T>(
  current: Promise<ApiResponse<T>> | null,
  fetcher: () => Promise<ApiResponse<T>>,
  onClear: () => void,
): Promise<ApiResponse<T>> {
  if (current) return current;
  const p = fetcher().then((r) => {
    if (r.error) onClear();   // failed request — drop cache so retry works
    return r;
  });
  return p;
}

export function fetchUniverses(opts?: CacheOpts) {
  if (opts?.force) _universeCache = null;
  if (!_universeCache) {
    _universeCache = _wrapCache(
      _universeCache,
      () => fetchJson<UniverseListResponse>("/data/universe"),
      () => { _universeCache = null; },
    );
  }
  return _universeCache;
}

export function fetchOperandCatalog(opts?: CacheOpts) {
  if (opts?.force) _catalogCache = null;
  if (!_catalogCache) {
    _catalogCache = _wrapCache(
      _catalogCache,
      () => fetchJson<OperandCatalogResponse>("/data/operands"),
      () => { _catalogCache = null; },
    );
  }
  return _catalogCache;
}

export function fetchCoverage(
  universeId = "SP500_subset",
  opts?: CacheOpts,
) {
  if (opts?.force) _coverageCache.delete(universeId);
  let p = _coverageCache.get(universeId);
  if (!p) {
    p = fetchJson<CoverageResponse>(
      `/data/coverage?universe_id=${encodeURIComponent(universeId)}`,
    ).then((r) => {
      if (r.error) _coverageCache.delete(universeId);
      return r;
    });
    _coverageCache.set(universeId, p);
  }
  return p;
}

/** Invalidate all Data-module caches in one call (manual refresh). */
export function invalidateDataCache() {
  _universeCache = null;
  _catalogCache = null;
  _coverageCache.clear();
}

/* ── P3: Signal Layer ── */

export function signalToday(spec: SignalSpec, top_n = 10) {
  return fetchJson<SignalTodayResponse>("/signal/today", {
    method: "POST",
    body: JSON.stringify({ spec, top_n }),
  });
}

export function signalIcTimeseries(spec: SignalSpec, lookback = 60) {
  return fetchJson<ICTimeseriesResponse>("/signal/ic_timeseries", {
    method: "POST",
    body: JSON.stringify({ spec, lookback }),
  });
}

export function signalExposure(spec: SignalSpec, top_n = 10) {
  return fetchJson<ExposureResponse>("/signal/exposure", {
    method: "POST",
    body: JSON.stringify({ spec, top_n }),
  });
}
