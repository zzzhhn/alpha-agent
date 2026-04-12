"use client";

import { usePolling } from "./usePolling";
import {
  getServiceHealth,
  getPipelineLatency,
  getThroughput,
  getGatewayStatus,
  getAuditDecisions,
  getSystemConfig,
} from "@/lib/api";
import type {
  ApiResponse,
  ServiceHealthResponse,
  PipelineLatency,
  ThroughputMetrics,
  GatewayStatus,
  AuditSummary,
  SystemConfig,
} from "@/lib/types";

export function useServiceHealth() {
  return usePolling<ApiResponse<ServiceHealthResponse>>({
    fetcher: getServiceHealth,
    intervalMs: 2_000,
  });
}

export function usePipelineLatency() {
  return usePolling<ApiResponse<PipelineLatency>>({
    fetcher: getPipelineLatency,
    intervalMs: 5_000,
  });
}

export function useThroughput() {
  return usePolling<ApiResponse<ThroughputMetrics>>({
    fetcher: getThroughput,
    intervalMs: 10_000,
  });
}

export function useGatewayStatus() {
  return usePolling<ApiResponse<GatewayStatus>>({
    fetcher: getGatewayStatus,
    intervalMs: 5_000,
  });
}

export function useAuditDecisions() {
  return usePolling<ApiResponse<AuditSummary>>({
    fetcher: getAuditDecisions,
    intervalMs: 10_000,
  });
}

export function useSystemConfig() {
  return usePolling<ApiResponse<SystemConfig>>({
    fetcher: getSystemConfig,
    intervalMs: 10_000,
  });
}
