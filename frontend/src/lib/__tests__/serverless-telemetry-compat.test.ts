import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getPipelineLatency,
  getServiceHealth,
  getServiceHealthById,
  getSystemConfig,
  getThroughput,
  normalizePipelineLatency,
  normalizeServiceHealthResponse,
  normalizeSystemConfig,
  normalizeThroughputMetrics,
} from "@/lib/api";

describe("serverless telemetry client compatibility (U05)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("preserves explicit unavailable states without fabricating 0 or demo numbers", () => {
    expect(
      normalizePipelineLatency({
        availability: "unavailable",
        source: "untracked_serverless_compat",
        sampled_at: null,
        segments: [],
        total_ms: null,
        timestamp: null,
      }),
    ).toEqual({
      availability: "unavailable",
      source: "untracked_serverless_compat",
      sampled_at: null,
      segments: [],
      total_ms: null,
      timestamp: null,
    });

    expect(
      normalizeThroughputMetrics({
        availability: "unavailable",
        source: "untracked_serverless_compat",
        sampled_at: null,
        tickers_per_sec: null,
        trades_per_sec: null,
        features_per_sec: null,
        timestamp: null,
      }),
    ).toEqual({
      availability: "unavailable",
      source: "untracked_serverless_compat",
      sampled_at: null,
      tickers_per_sec: null,
      trades_per_sec: null,
      features_per_sec: null,
      timestamp: null,
    });

    expect(
      normalizeSystemConfig({
        availability: "unavailable",
        source: "untracked_serverless_compat",
        sampled_at: null,
        api_calls_24h: null,
        cache_hit_rate: null,
        avg_latency_ms: null,
        error_count_24h: null,
        alerts: [],
      }),
    ).toEqual({
      availability: "unavailable",
      source: "untracked_serverless_compat",
      sampled_at: null,
      api_calls_24h: null,
      cache_hit_rate: null,
      avg_latency_ms: null,
      error_count_24h: null,
      alerts: [],
    });
  });

  it("stays compatible with missing/partial fields from older or minimal payloads", () => {
    expect(normalizePipelineLatency({})).toEqual({
      availability: "unavailable",
      source: null,
      sampled_at: null,
      segments: [],
      total_ms: null,
      timestamp: null,
    });

    expect(normalizeThroughputMetrics({ tickers_per_sec: 3.2 })).toEqual({
      availability: "unavailable",
      source: null,
      sampled_at: null,
      tickers_per_sec: null,
      trades_per_sec: null,
      features_per_sec: null,
      timestamp: null,
    });

    expect(normalizeSystemConfig({ alerts: [] })).toEqual({
      availability: "unavailable",
      source: null,
      sampled_at: null,
      api_calls_24h: null,
      cache_hit_rate: null,
      avg_latency_ms: null,
      error_count_24h: null,
      alerts: [],
    });

    const legacyLatency = normalizePipelineLatency({
      segments: [{ stage: "llm_decision", latency_ms: 410, percentage: 100 }],
      total_ms: 410,
      timestamp: "2026-11-26T14:00:00+00:00",
    });
    expect(legacyLatency).toEqual({
      availability: "measured",
      source: null,
      sampled_at: "2026-11-26T14:00:00+00:00",
      segments: [{ stage: "llm_decision", latency_ms: 410, percentage: 100 }],
      total_ms: 410,
      timestamp: "2026-11-26T14:00:00+00:00",
    });

    const singleSvc = normalizeServiceHealthResponse({
      service_id: "fastapi",
      status: "green",
      availability: "unavailable",
      source: "runtime_probe_only",
      latency_p95_ms: 45,
      uptime_pct_24h: 99.9,
      last_check_at: "2026-11-26T14:00:00+00:00",
    });
    expect(singleSvc.availability).toBe("unavailable");
    expect(singleSvc.services).toHaveLength(1);
    expect(singleSvc.services[0].latency_p95_ms).toBeNull();
    expect(singleSvc.services[0].uptime_pct_24h).toBeNull();
  });

  it("normalizes fetch responses across measured, demo, and unavailable endpoints", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/pipelines/latency")) {
        return new Response(
          JSON.stringify({
            availability: "demo",
            source: "demo_fixture",
            sampled_at: "2026-11-26T12:00:00+00:00",
            segments: [{ stage: "llm_decision", latency_ms: 900, percentage: 100 }],
            total_ms: 900,
            timestamp: "2026-11-26T12:00:00+00:00",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/metrics/throughput")) {
        return new Response(
          JSON.stringify({
            availability: "unavailable",
            source: "untracked_serverless_compat",
            sampled_at: null,
            tickers_per_sec: null,
            trades_per_sec: null,
            features_per_sec: null,
            timestamp: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/services/health") || url.endsWith("/services/fastapi/health")) {
        return new Response(
          JSON.stringify({
            availability: "measured",
            source: "service_telemetry",
            sampled_at: "2026-11-26T14:30:00+00:00",
            services: [
              {
                service_id: "fastapi",
                status: "green",
                availability: "measured",
                source: "http_hist",
                sampled_at: "2026-11-26T14:30:00+00:00",
                latency_p95_ms: 38.4,
                uptime_pct_24h: 99.95,
                last_check_at: "2026-11-26T14:30:00+00:00",
                last_error_at: null,
              },
              {
                service_id: "llm_kimi",
                status: "yellow",
                availability: "unavailable",
                source: "runtime_probe_only",
                sampled_at: null,
                latency_p95_ms: null,
                uptime_pct_24h: null,
                last_check_at: null,
                last_error_at: null,
              },
            ],
            timestamp: "2026-11-26T14:30:00+00:00",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          availability: "measured",
          source: "edge_log_rollup",
          sampled_at: "2026-11-26T14:30:00+00:00",
          api_calls_24h: 318,
          cache_hit_rate: 0.75,
          avg_latency_ms: 84.3,
          error_count_24h: 1,
          alerts: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const [lat, thr, svc, svcById, cfg] = await Promise.all([
      getPipelineLatency(),
      getThroughput(),
      getServiceHealth(),
      getServiceHealthById("fastapi"),
      getSystemConfig(),
    ]);

    expect(lat.data?.availability).toBe("demo");
    expect(lat.data?.source).toBe("demo_fixture");
    expect(lat.data?.total_ms).toBe(900);

    expect(thr.data?.availability).toBe("unavailable");
    expect(thr.data?.tickers_per_sec).toBeNull();
    expect(thr.data?.sampled_at).toBeNull();

    expect(svc.data?.availability).toBe("measured");
    expect(svc.data?.services[0].latency_p95_ms).toBe(38.4);
    expect(svc.data?.services[1].availability).toBe("unavailable");
    expect(svc.data?.services[1].latency_p95_ms).toBeNull();
    expect(svcById.data?.services).toHaveLength(2);

    expect(cfg.data?.availability).toBe("measured");
    expect(cfg.data?.api_calls_24h).toBe(318);
  });
});
