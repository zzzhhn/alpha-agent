import type {
  ApiResponse,
  TelemetryAvailability,
  ServiceHealthResponse,
  PipelineLatency,
  ThroughputMetrics,
  AlphaSignal,
  Order,
  AuditEvent,
  MarketIndicators,
  FeatureState,
  AlphaFactor,
  AlphaFactorSummary,
  GatewayStatus,
  GateRule,
  SystemConfig,
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
  ScreenerRequest,
  ScreenerResponse,
  ExplainAstResponse,
  ZooCorrelationRequest,
  ZooCorrelationResponse,
} from "./types";

// Browser: same-origin "" so /api/* goes through the Next.js middleware
// (which injects the auth Bearer header) and the next.config.mjs rewrite.
// Server (SSR): the absolute backend URL, since middleware does not run on
// server-component fetches. Auth-gated endpoints are only called client-side.
const BASE_URL =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6008"
    : "";
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
  // Phase 4: credentials:"include" carries the NextAuth JWT cookie on
  // same-origin requests; the Next.js rewrite forwards it to FastAPI as the
  // Authorization Bearer token. The old X-LLM-* byokHeaders() injection is
  // gone - the backend now reads the BYOK key server-side from user_byok.
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!response.ok) {
    // HTTP/2 strips response.statusText, so it's almost always empty in
    // production. The backend (FastAPI HTTPException) puts the actual
    // diagnostic in the response body as {"detail": "..."}. Read it
    // before throwing so the user sees the root cause, not just "HTTP 500:".
    let detail = response.statusText;
    try {
      const text = await response.text();
      if (text) {
        try {
          const parsed = JSON.parse(text) as { detail?: unknown };
          if (typeof parsed?.detail === "string") {
            detail = parsed.detail;
          } else if (parsed?.detail != null) {
            detail = JSON.stringify(parsed.detail);
          } else {
            detail = text.slice(0, 500);
          }
        } catch {
          detail = text.slice(0, 500);
        }
      }
    } catch {
      // body unreadable — keep statusText (possibly empty)
    }
    throw new ApiError(
      `HTTP ${response.status}: ${detail || "(no body)"}`,
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

function _nonNegativeFinite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

function _telemetryAvailability(
  raw: unknown,
  hasMeasurements: boolean,
): TelemetryAvailability {
  if (raw === undefined || raw === null) {
    return hasMeasurements ? "measured" : "unavailable";
  }
  if (raw === "demo" || raw === "measured") {
    return hasMeasurements ? raw : "unavailable";
  }
  return "unavailable";
}

function _nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function _isoTimestamp(value: unknown): string | null {
  const text = _nonEmptyString(value);
  if (!text || (!text.includes("T") && !text.includes("t") && !text.includes(" "))) {
    return null;
  }
  const ms = Date.parse(text);
  return Number.isFinite(ms) ? text : null;
}

export function normalizeServiceHealthResponse(
  raw: (Partial<ServiceHealthResponse> & Partial<{
    service_id: string;
    status: string;
    availability: TelemetryAvailability;
    source: string | null;
    sampled_at: string | null;
    latency_p95_ms: number | null;
    uptime_pct_24h: number | null;
    probe_latency_ms: number | null;
    last_check_at: string | null;
    last_error_at: string | null;
  }>) | null | undefined,
): ServiceHealthResponse {
  const rawServices = Array.isArray(raw?.services)
    ? raw.services
    : raw && typeof raw.service_id === "string"
      ? [raw]
      : [];
  const forceTopUnavailable =
    raw?.availability !== undefined &&
    raw?.availability !== null &&
    raw.availability !== "measured" &&
    raw.availability !== "demo";
  const services = rawServices
        .filter((svc): svc is NonNullable<typeof svc> => Boolean(svc && typeof svc.service_id === "string"))
        .map((svc) => {
          const latency = _nonNegativeFinite(svc.latency_p95_ms);
          const uptime = _nonNegativeFinite(svc.uptime_pct_24h);
          const sampledAt = _isoTimestamp(svc.sampled_at);
          const availability = forceTopUnavailable
            ? "unavailable"
            : _telemetryAvailability(
                svc.availability,
                latency !== null || uptime !== null,
              );
          return {
            service_id: svc.service_id,
            status: svc.status === "green" || svc.status === "yellow" || svc.status === "red"
              ? svc.status
              : "yellow",
            availability,
            source: _nonEmptyString(svc.source),
            sampled_at: availability === "unavailable" ? null : sampledAt,
            latency_p95_ms: availability === "unavailable" ? null : latency,
            uptime_pct_24h: availability === "unavailable" ? null : uptime,
            probe_latency_ms: _nonNegativeFinite(svc.probe_latency_ms),
            last_check_at: _isoTimestamp(svc.last_check_at),
            last_error_at: _isoTimestamp(svc.last_error_at),
          };
        });
  const hasMeasuredService = services.some((svc) => svc.availability === "measured");
  const hasDemoService = services.some((svc) => svc.availability === "demo");
  const availability = _telemetryAvailability(
    raw?.availability ?? (hasDemoService ? "demo" : undefined),
    hasMeasuredService || hasDemoService,
  );
  const sampledAt = _isoTimestamp(raw?.sampled_at) ?? _isoTimestamp(raw?.timestamp);
  return {
    availability,
    source: _nonEmptyString(raw?.source),
    sampled_at: availability === "unavailable" ? null : sampledAt,
    services,
    timestamp: availability === "unavailable" ? null : (_isoTimestamp(raw?.timestamp) ?? sampledAt),
  };
}

export function normalizePipelineLatency(
  raw: Partial<PipelineLatency> | null | undefined,
): PipelineLatency {
  const segments = Array.isArray(raw?.segments)
    ? raw.segments
        .filter((seg): seg is NonNullable<typeof seg> => Boolean(seg && typeof seg.stage === "string"))
        .flatMap((seg) => {
          const latencyMs = _nonNegativeFinite(seg.latency_ms);
          const percentage = _nonNegativeFinite(seg.percentage);
          if (latencyMs === null) return [];
          return [{
            stage: seg.stage,
            latency_ms: latencyMs,
            percentage: percentage ?? 0,
          }];
        })
    : [];
  const totalMs = _nonNegativeFinite(raw?.total_ms);
  const sampledAt = _isoTimestamp(raw?.sampled_at) ?? _isoTimestamp(raw?.timestamp);
  const availability = _telemetryAvailability(
    raw?.availability,
    segments.length > 0 && totalMs !== null && sampledAt !== null,
  );
  if (availability === "unavailable") {
    return {
      availability: "unavailable",
      source: _nonEmptyString(raw?.source),
      sampled_at: null,
      segments: [],
      total_ms: null,
      timestamp: null,
    };
  }
  return {
    availability,
    source: _nonEmptyString(raw?.source),
    sampled_at: sampledAt,
    segments,
    total_ms: totalMs,
    timestamp: _isoTimestamp(raw?.timestamp) ?? sampledAt,
  };
}

export function normalizeThroughputMetrics(
  raw: Partial<ThroughputMetrics> | null | undefined,
): ThroughputMetrics {
  const tickers = _nonNegativeFinite(raw?.tickers_per_sec);
  const trades = _nonNegativeFinite(raw?.trades_per_sec);
  const features = _nonNegativeFinite(raw?.features_per_sec);
  const sampledAt = _isoTimestamp(raw?.sampled_at) ?? _isoTimestamp(raw?.timestamp);
  const availability = _telemetryAvailability(
    raw?.availability,
    tickers !== null && trades !== null && features !== null && sampledAt !== null,
  );
  if (availability === "unavailable") {
    return {
      availability: "unavailable",
      source: _nonEmptyString(raw?.source),
      sampled_at: null,
      tickers_per_sec: null,
      trades_per_sec: null,
      features_per_sec: null,
      timestamp: null,
    };
  }
  return {
    availability,
    source: _nonEmptyString(raw?.source),
    sampled_at: sampledAt,
    tickers_per_sec: tickers,
    trades_per_sec: trades,
    features_per_sec: features,
    timestamp: _isoTimestamp(raw?.timestamp) ?? sampledAt,
  };
}

export function normalizeSystemConfig(
  raw: Partial<SystemConfig> | null | undefined,
): SystemConfig {
  const apiCalls = _nonNegativeFinite(raw?.api_calls_24h);
  const hitRate = _nonNegativeFinite(raw?.cache_hit_rate);
  const avgLatency = _nonNegativeFinite(raw?.avg_latency_ms);
  const errorCount = _nonNegativeFinite(raw?.error_count_24h);
  const alerts = Array.isArray(raw?.alerts) ? raw.alerts : [];
  const sampledAt = _isoTimestamp(raw?.sampled_at);
  const availability = _telemetryAvailability(
    raw?.availability,
    apiCalls !== null && hitRate !== null && avgLatency !== null && errorCount !== null && sampledAt !== null,
  );
  if (availability === "unavailable") {
    return {
      availability: "unavailable",
      source: _nonEmptyString(raw?.source),
      sampled_at: null,
      api_calls_24h: null,
      cache_hit_rate: null,
      avg_latency_ms: null,
      error_count_24h: null,
      alerts,
    };
  }
  return {
    availability,
    source: _nonEmptyString(raw?.source),
    sampled_at: sampledAt,
    api_calls_24h: apiCalls,
    cache_hit_rate: hitRate,
    avg_latency_ms: avgLatency,
    error_count_24h: errorCount,
    alerts,
  };
}

export function getServiceHealth() {
  return fetchJson<Partial<ServiceHealthResponse>>("/services/health").then((res) =>
    res.data ? { ...res, data: normalizeServiceHealthResponse(res.data) } : { ...res, data: null },
  );
}

export function getServiceHealthById(serviceId: string) {
  return fetchJson<Partial<ServiceHealthResponse>>(
    `/services/${encodeURIComponent(serviceId)}/health`
  ).then((res) =>
    res.data ? { ...res, data: normalizeServiceHealthResponse(res.data) } : { ...res, data: null },
  );
}

export function getPipelineLatency() {
  return fetchJson<Partial<PipelineLatency>>("/pipelines/latency").then((res) =>
    res.data ? { ...res, data: normalizePipelineLatency(res.data) } : { ...res, data: null },
  );
}

export function getThroughput() {
  return fetchJson<Partial<ThroughputMetrics>>("/metrics/throughput").then((res) =>
    res.data ? { ...res, data: normalizeThroughputMetrics(res.data) } : { ...res, data: null },
  );
}

export function getAlphaSignals() {
  return fetchJson<readonly AlphaSignal[]>("/alpha/signals");
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

/* ═══════════════════ Orders ═══════════════════ */

export function getPendingOrders() {
  return fetchJson<readonly Order[]>("/orders/pending");
}

/* ═══════════════════ Gateway ═══════════════════ */

export function getGatewayStatus() {
  return fetchJson<GatewayStatus>("/gateway/status");
}

export function getGatewayRules() {
  return fetchJson<readonly GateRule[]>("/gateway/rules");
}

/* ═══════════════════ System ═══════════════════ */

export function getSystemConfig() {
  return fetchJson<Partial<SystemConfig>>("/system/config").then((res) =>
    res.data ? { ...res, data: normalizeSystemConfig(res.data) } : { ...res, data: null },
  );
}

/* ═══════════════════ Interactive (POST) ═══════════════════ */
//
// Legacy single-ticker endpoints (RSI/MACD/Bollinger backtest, ticker
// search, factor analytics by ticker, gate simulation, portfolio stress
// test) were removed in P4.1 / P6.A. They didn't fit the cross-sectional
// factor research mental model.

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

/* ── D1: Multi-factor Screener ── */

export function runScreener(params: ScreenerRequest) {
  return fetchJson<ScreenerResponse>("/screener/run", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/* ── B3: AST visualization ── */

export function explainAst(expression: string) {
  return fetchJson<ExplainAstResponse>("/factor/explain_ast", {
    method: "POST",
    body: JSON.stringify({ expression }),
  });
}

/* ── T2.1: Zoo cross-correlation ── */

export function runZooCorrelation(params: ZooCorrelationRequest) {
  return fetchJson<ZooCorrelationResponse>("/zoo/correlation", {
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

// P3-2: the in-memory promise cache below survives client-side navigation
// but resets on a full page reload, so the heavy /data/universe + coverage
// endpoints (~12s cold) pay the cost again on every hard refresh. Persist
// them in localStorage too — the panel is static (changes only on a
// parquet rebuild + redeploy), so a 6h TTL is safe and makes hard reloads
// instant.
const _LS_TTL_MS = 6 * 60 * 60 * 1000;
const _LS_UNIVERSE = "alphacore.data.universe.v1";
const _LS_COVERAGE_PREFIX = "alphacore.data.coverage.v1.";

function _lsGet<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { at: number; data: T };
    if (Date.now() - parsed.at > _LS_TTL_MS) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

function _lsSet<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify({ at: Date.now(), data }));
  } catch {
    // storage full / disabled — in-memory cache still applies
  }
}

function _lsDel(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

function _okResponse<T>(data: T): ApiResponse<T> {
  return { data, error: null, timestamp: new Date().toISOString() };
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
  if (opts?.force) {
    _universeCache = null;
    _lsDel(_LS_UNIVERSE);
  }
  if (!_universeCache) {
    const cached = opts?.force ? null : _lsGet<UniverseListResponse>(_LS_UNIVERSE);
    if (cached) {
      _universeCache = Promise.resolve(_okResponse(cached));
    } else {
      _universeCache = _wrapCache(
        _universeCache,
        () =>
          fetchJson<UniverseListResponse>("/data/universe").then((r) => {
            if (r.data) _lsSet(_LS_UNIVERSE, r.data);
            return r;
          }),
        () => { _universeCache = null; },
      );
    }
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

/** B1: Fetch operands catalog augmented with operator signatures + source
 *  snippets. NOT cached — only the Methodology page calls this and the
 *  payload is heavy. */
export function fetchOperandCatalogWithSignatures() {
  return fetchJson<OperandCatalogResponse>("/data/operands?include_signature=true");
}

/** B1: Canonical sector strings present in the active panel. Used by the
 *  Methodology Data tab and Screener autocomplete. */
export function fetchSectors() {
  return fetchJson<{ sectors: readonly string[]; panel_has_sector: boolean }>(
    "/data/sectors",
  );
}

export function fetchCoverage(
  universeId = "SP500_subset",
  opts?: CacheOpts,
) {
  const lsKey = _LS_COVERAGE_PREFIX + universeId;
  if (opts?.force) {
    _coverageCache.delete(universeId);
    _lsDel(lsKey);
  }
  let p = _coverageCache.get(universeId);
  if (!p) {
    const cached = opts?.force ? null : _lsGet<CoverageResponse>(lsKey);
    if (cached) {
      p = Promise.resolve(_okResponse(cached));
    } else {
      p = fetchJson<CoverageResponse>(
        `/data/coverage?universe_id=${encodeURIComponent(universeId)}`,
      ).then((r) => {
        if (r.error) _coverageCache.delete(universeId);
        else if (r.data) _lsSet(lsKey, r.data);
        return r;
      });
    }
    _coverageCache.set(universeId, p);
  }
  return p;
}

/** Invalidate all Data-module caches in one call (manual refresh). */
export function invalidateDataCache() {
  _universeCache = null;
  _catalogCache = null;
  _coverageCache.clear();
  _lsDel(_LS_UNIVERSE);
  if (typeof window !== "undefined") {
    try {
      // Clear every persisted coverage entry (any universeId).
      Object.keys(window.localStorage)
        .filter((k) => k.startsWith(_LS_COVERAGE_PREFIX))
        .forEach((k) => window.localStorage.removeItem(k));
    } catch {
      // ignore
    }
  }
}

/* ── P3: Signal Layer ── */

export function signalToday(
  spec: SignalSpec, top_n = 10, neutralize: "none" | "sector" = "none",
) {
  return fetchJson<SignalTodayResponse>("/signal/today", {
    method: "POST",
    body: JSON.stringify({ spec, top_n, neutralize }),
  });
}

export function signalIcTimeseries(
  spec: SignalSpec, lookback = 60, neutralize: "none" | "sector" = "none",
) {
  return fetchJson<ICTimeseriesResponse>("/signal/ic_timeseries", {
    method: "POST",
    body: JSON.stringify({ spec, lookback, neutralize }),
  });
}

export function signalExposure(
  spec: SignalSpec, top_n = 10, neutralize: "none" | "sector" = "none",
) {
  return fetchJson<ExposureResponse>("/signal/exposure", {
    method: "POST",
    body: JSON.stringify({ spec, top_n, neutralize }),
  });
}

/* ── Bundle B (T4.1): Factor Performance DB ── */

export interface ServerFactor {
  readonly id: string;
  readonly ast_hash: string;
  readonly name: string;
  readonly expression: string;
  readonly hypothesis?: string | null;
  readonly intuition?: string | null;
  readonly last_direction?: string | null;
  readonly last_neutralize?: string | null;
  readonly last_benchmark?: string | null;
  readonly last_test_sharpe?: number | null;
  readonly last_test_ic?: number | null;
  readonly last_alpha_t?: number | null;
  readonly last_alpha_p?: number | null;
  readonly last_psr?: number | null;
  readonly last_overfit_flag?: boolean | null;
  readonly n_runs: number;
  readonly created_at?: string | null;
  readonly updated_at?: string | null;
}

export interface ServerFactorRun {
  readonly id: string;
  readonly factor_id: string;
  readonly panel_version: string;
  readonly direction: string;
  readonly neutralize: string;
  readonly benchmark_ticker: string;
  readonly top_pct: number;
  readonly bottom_pct: number;
  readonly transaction_cost_bps: number;
  readonly test_sharpe: number;
  readonly test_ic: number;
  readonly test_psr?: number | null;
  readonly alpha_annualized?: number | null;
  readonly alpha_t?: number | null;
  readonly alpha_p?: number | null;
  readonly beta?: number | null;
  readonly r_squared?: number | null;
  readonly overfit_flag: boolean;
  readonly daily_ic?: readonly number[] | null;
  readonly ran_at?: string | null;
}

export interface DecayAlert {
  readonly factor_id: string;
  readonly name: string;
  readonly expression: string;
  readonly n_runs: number;
  readonly baseline_ic: number;
  readonly latest_ic: number;
  readonly decay_pct: number;
  readonly latest_run_at: string;
}

export function listServerFactors(limit = 100) {
  return fetchJson<ServerFactor[]>(`/factors?limit=${limit}`);
}

export function getServerFactor(factorId: string) {
  return fetchJson<{ factor: ServerFactor; runs: ServerFactorRun[] }>(
    `/factors/${encodeURIComponent(factorId)}`,
  );
}

export function deleteServerFactor(factorId: string) {
  return fetchJson<{ deleted: string }>(
    `/factors/${encodeURIComponent(factorId)}`,
    { method: "DELETE" },
  );
}

export function getDecayAlerts(opts?: {
  rolling_window_days?: number;
  min_runs?: number;
  decay_threshold?: number;
}) {
  const params = new URLSearchParams();
  if (opts?.rolling_window_days) params.set("rolling_window_days", String(opts.rolling_window_days));
  if (opts?.min_runs) params.set("min_runs", String(opts.min_runs));
  if (opts?.decay_threshold) params.set("decay_threshold", String(opts.decay_threshold));
  const qs = params.toString();
  return fetchJson<DecayAlert[]>(`/factors/decay_alerts${qs ? "?" + qs : ""}`);
}
