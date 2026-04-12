"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { KPICard } from "@/components/ui/KPICard";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  useServiceHealth,
  usePipelineLatency,
  useSystemConfig,
} from "@/hooks/useDashboard";
import type { ServiceStatus, AlertSeverity } from "@/lib/types";
import clsx from "clsx";

/* ── Inline ServiceCard ── */

interface ServiceCardProps {
  readonly name: string;
  readonly status: ServiceStatus;
  readonly latencyMs: number;
  readonly uptimePct: number;
}

const SL: Record<ServiceStatus, string> = { green: "Healthy", yellow: "Degraded", red: "Down" };
const SD: Record<ServiceStatus, string> = { green: "bg-green", yellow: "bg-yellow", red: "bg-red animate-pulse" };

function ServiceCard({ name, status, latencyMs, uptimePct }: ServiceCardProps) {
  return (
    <div className="glass-inner flex items-start gap-3 p-3" role="group" aria-label={name}>
      <span className={clsx("mt-1 h-2.5 w-2.5 shrink-0 rounded-full", SD[status])} aria-label={`Status: ${SL[status]}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-text">{name}</span>
          <Badge variant={status} size="sm">{SL[status]}</Badge>
        </div>
        <div className="mt-1 flex gap-3 text-[11px] text-muted">
          <span>Latency: {latencyMs}ms</span>
          <span>Uptime: {uptimePct}%</span>
        </div>
      </div>
    </div>
  );
}

/* ── Alert severity badge variant ── */

function severityVariant(sev: AlertSeverity) {
  if (sev === "CRITICAL" || sev === "ERROR") return "red" as const;
  if (sev === "WARN") return "yellow" as const;
  return "muted" as const;
}

/* ── Fallback data ── */

const fb = (id: string, s: ServiceStatus, l: number, u: number) =>
  ({ service_id: id, status: s, latency_p95_ms: l, uptime_pct_24h: u });
const FALLBACK_SERVICES = [
  fb("fastapi", "green", 42, 99.98), fb("llm_api", "yellow", 1850, 99.5),
  fb("yfinance", "green", 120, 99.9), fb("akshare", "green", 95, 98.8),
  fb("sqlite", "green", 3, 100), fb("model_store", "green", 15, 100),
];
const FALLBACK_ALERTS = [
  { timestamp: "14:30:15Z", severity: "WARN" as const, service: "llm_api", message: "P95 latency > 1500ms" },
  { timestamp: "13:45:02Z", severity: "INFO" as const, service: "fastapi", message: "Cache cleared" },
  { timestamp: "12:10:44Z", severity: "ERROR" as const, service: "akshare", message: "Rate limit hit" },
];

export default function SystemPage() {
  const { data: healthData, error: healthError } = useServiceHealth();
  const { data: latencyData } = usePipelineLatency();
  const { data: configData, isLoading } = useSystemConfig();

  const services = healthData?.data?.services ?? FALLBACK_SERVICES;
  const segments = latencyData?.data?.segments ?? [];
  const totalMs = latencyData?.data?.total_ms ?? 0;
  const config = configData?.data;
  const alerts = config?.alerts ?? FALLBACK_ALERTS;

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold text-text">
        {"\uD83D\uDDA5\uFE0F"} System Monitor
      </h1>

      {/* Throughput KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <KPICard
          label="API Calls / 24h"
          value={isLoading ? "..." : String(config?.api_calls_24h ?? "12,847")}
          delta={{ value: "+5.2%", direction: "up" }}
        />
        <KPICard
          label="Cache Hit Rate"
          value={isLoading ? "..." : `${config?.cache_hit_rate ?? 94.2}%`}
          status="green"
        />
        <KPICard
          label="Avg Latency"
          value={isLoading ? "..." : `${config?.avg_latency_ms ?? 245}ms`}
          tooltip="Pipeline end-to-end P95"
        />
        <KPICard
          label="Errors (24h)"
          value={isLoading ? "..." : String(config?.error_count_24h ?? 3)}
          status={(config?.error_count_24h ?? 3) > 5 ? "red" : "yellow"}
        />
      </div>

      {/* Service Health Grid */}
      <Card>
        <CardHeader
          title="Service Health"
          icon={"\uD83D\uDFE2"}
          subtitle="Real-time service status (2s polling)"
        />
        {healthError && services === FALLBACK_SERVICES ? (
          <EmptyState title="Connection Error" description={healthError} />
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {services.map((svc) => (
              <ServiceCard
                key={svc.service_id}
                name={svc.service_id}
                status={svc.status}
                latencyMs={svc.latency_p95_ms}
                uptimePct={svc.uptime_pct_24h}
              />
            ))}
          </div>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-5">
        {/* Pipeline Latency Breakdown */}
        <Card>
          <CardHeader
            title="Pipeline Latency"
            icon={"\u23F1\uFE0F"}
            subtitle={totalMs > 0 ? `Total: ${totalMs}ms` : "Awaiting data"}
          />
          {segments.length === 0 ? (
            <EmptyState title="No latency data" description="Pipeline has not reported yet" />
          ) : (
            <div className="space-y-2">
              {segments.map((seg) => (
                <div key={seg.stage} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-xs font-semibold text-text">
                    {seg.stage}
                  </span>
                  <div className="relative h-5 flex-1 overflow-hidden rounded bg-border/30">
                    <div
                      className="absolute inset-y-0 left-0 rounded bg-accent/70"
                      style={{ width: `${Math.min(seg.percentage, 100)}%` }}
                    />
                    <span className="relative z-10 flex h-full items-center px-2 text-[10px] font-mono text-text">
                      {seg.latency_ms}ms ({seg.percentage}%)
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Alert Feed */}
        <Card>
          <CardHeader
            title="Alert Feed"
            icon={"\uD83D\uDD14"}
            subtitle="Recent system alerts"
          />
          {alerts.length === 0 ? (
            <EmptyState title="No alerts" description="System operating normally" />
          ) : (
            <div className="max-h-64 space-y-2 overflow-y-auto">
              {alerts.map((alert, idx) => (
                <div key={`${alert.timestamp}-${idx}`} className="glass-inner flex items-start gap-2 p-2">
                  <Badge variant={severityVariant(alert.severity)} size="sm">
                    {alert.severity}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-text">{alert.message}</div>
                    <div className="mt-0.5 text-[10px] text-muted">
                      {alert.service} &middot; {alert.timestamp}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
