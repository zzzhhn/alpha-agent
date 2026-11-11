"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useSession } from "next-auth/react";
import { apiGet } from "@/lib/api/client";
import { usePolling } from "@/hooks/usePolling";
import { useLocale } from "./LocaleProvider";
import { TmServiceStatus, type ServiceState } from "@/components/tm/TmServiceStatus";
import { readCachedServiceHealth, readSystemHealth, serializeServiceHealthCache, SERVICE_HEALTH_CACHE_KEY } from "@/lib/service-health";
import type { AlertAttention, NavStatusResponse } from "@/lib/nav-status";

type HealthState = ServiceState;
const HealthContext = createContext<HealthState>("checking");
const AdminContext = createContext(false);
export const useAdminAccess = () => useContext(AdminContext);

export interface NavStatusValue {
  readonly status: NavStatusResponse | null;
  readonly statusFailed: boolean;
  readonly attention: AlertAttention | null;
  readonly attentionState: "signed_out" | "error" | "ok" | "loading";
}
const NavStatusContext = createContext<NavStatusValue>({
  status: null, statusFailed: false, attention: null, attentionState: "loading",
});
export const useNavStatus = () => useContext(NavStatusContext);

// Snapshot freshness and scheduler state change at most a few times a day; the
// public read is edge cached for two minutes, so a five-minute visible-tab
// poll stays well below the existing 60s health poll.
const NAV_STATUS_INTERVAL_MS = 300_000;
const readNavStatus = () => apiGet<NavStatusResponse>("/api/nav/status", { timeoutMs: 12_000 });
const readAttention = () => apiGet<AlertAttention>("/api/alerts/attention", { timeoutMs: 12_000 });

/** One visible-tab poll shared by topbar and sidebar, not one poll per badge. */
export function SystemHealthProvider({ children }: { children: ReactNode }) {
  const { data, error, lastUpdated } = usePolling({ fetcher: readSystemHealth, intervalMs: 60_000 });
  const [cachedHealth, setCachedHealth] = useState<HealthState>("checking");
  useEffect(() => {
    // Read after hydration so SSR and the first client render agree. A fresh
    // cache replaces "checking" immediately on mount while the poll runs.
    try {
      setCachedHealth(readCachedServiceHealth(window.sessionStorage.getItem(SERVICE_HEALTH_CACHE_KEY)) ?? "checking");
    } catch {
      // Storage may be disabled; the live health read still works.
    }
  }, []);
  useEffect(() => {
    if (!data || !lastUpdated) return;
    const cached = serializeServiceHealthCache(data, new Date(lastUpdated).getTime());
    if (!cached) return;
    try { window.sessionStorage.setItem(SERVICE_HEALTH_CACHE_KEY, cached); } catch { /* optional cache */ }
  }, [data, lastUpdated]);
  const nav = usePolling({ fetcher: readNavStatus, intervalMs: NAV_STATUS_INTERVAL_MS });
  const { status: session } = useSession();
  const signedIn = session === "authenticated";
  const alerts = usePolling({ fetcher: readAttention, intervalMs: NAV_STATUS_INTERVAL_MS, enabled: signedIn });
  const [admin, setAdmin] = useState(false);
  useEffect(() => {
    setAdmin(false);
    if (!signedIn) return;
    let alive = true;
    apiGet<{ is_admin: boolean }>("/api/user/me")
      .then((me) => { if (alive) setAdmin(me.is_admin === true); })
      .catch(() => { if (alive) setAdmin(false); });
    return () => { alive = false; };
  }, [signedIn]);
  const attentionState: NavStatusValue["attentionState"] =
    session === "loading" ? "loading"
      : !signedIn ? "signed_out"
        : alerts.error ? "error"
          : alerts.data ? "ok" : "loading";
  const navValue: NavStatusValue = {
    status: nav.data,
    // A failed latest read never keeps showing an older healthy state.
    statusFailed: Boolean(nav.error),
    attention: signedIn ? alerts.data : null,
    attentionState,
  };
  return (
    <HealthContext.Provider value={error ? "unknown" : data ?? cachedHealth}>
      <AdminContext.Provider value={signedIn && admin}>
        <NavStatusContext.Provider value={navValue}>{children}</NavStatusContext.Provider>
      </AdminContext.Provider>
    </HealthContext.Provider>
  );
}

export function AdminAccessNote() {
  const admin = useAdminAccess();
  const { locale } = useLocale();
  return admin ? null : <p className="px-3 py-2 text-xs text-tm-muted">
    {locale === "zh" ? "只读视图：全局策略与审批仅管理员可修改。" : "Read-only: global policy and approvals require the administrator."}
  </p>;
}

export function SystemHealthIndicator({ compact = false }: { readonly compact?: boolean }) {
  const state = useContext(HealthContext);
  const { locale } = useLocale();
  return (
    <Link href="/data" prefetch={false} className="inline-flex items-center gap-1.5 text-xs text-tm-muted hover:text-tm-fg focus-visible:outline focus-visible:outline-2 focus-visible:outline-tm-accent">
      <TmServiceStatus state={state} locale={locale} compact={compact} />
    </Link>
  );
}
