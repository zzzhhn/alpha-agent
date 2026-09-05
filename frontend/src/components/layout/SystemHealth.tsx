"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet } from "@/lib/api/client";
import { usePolling } from "@/hooks/usePolling";
import { useLocale } from "./LocaleProvider";
import { TmServiceStatus, type ServiceState } from "@/components/tm/TmServiceStatus";

type HealthState = ServiceState;
const HealthContext = createContext<HealthState>("checking");
const AdminContext = createContext(false);
export const useAdminAccess = () => useContext(AdminContext);

async function fetchHealth(): Promise<HealthState> {
  const [health, dag] = await Promise.all([
    apiGet<{ db: string }>("/api/_health", { timeoutMs: 12_000 }),
    apiGet<{ overall: string }>("/api/_health/dag", { timeoutMs: 12_000 }),
  ]);
  if (health.db !== "ok") return "unavailable";
  return dag.overall === "healthy" ? "healthy" : "degraded";
}

/** One visible-tab poll shared by topbar and sidebar, not one poll per badge. */
export function SystemHealthProvider({ children }: { children: ReactNode }) {
  const { data, error } = usePolling({ fetcher: fetchHealth, intervalMs: 60_000 });
  const [admin, setAdmin] = useState(false);
  useEffect(() => {
    let alive = true;
    apiGet<{ is_admin: boolean }>("/api/user/me")
      .then((me) => { if (alive) setAdmin(me.is_admin === true); })
      .catch(() => { if (alive) setAdmin(false); });
    return () => { alive = false; };
  }, []);
  return (
    <HealthContext.Provider value={error ? "unavailable" : data ?? "checking"}>
      <AdminContext.Provider value={admin}>{children}</AdminContext.Provider>
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

export function SystemHealthIndicator() {
  const state = useContext(HealthContext);
  const { locale } = useLocale();
  return (
    <Link href="/data" prefetch={false} className="inline-flex items-center gap-1.5 text-xs text-tm-muted hover:text-tm-fg">
      <TmServiceStatus state={state} locale={locale} />
    </Link>
  );
}
