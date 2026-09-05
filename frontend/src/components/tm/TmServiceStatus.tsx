import { type Locale } from "@/lib/i18n";

export type ServiceState = "checking" | "healthy" | "degraded" | "unavailable";
const TONES: Record<ServiceState, string> = {
  checking: "bg-tm-muted", healthy: "bg-tm-pos", degraded: "bg-tm-warn", unavailable: "bg-tm-neg",
};

export function TmServiceStatus({ state, locale }: { state: ServiceState; locale: Locale }) {
  const labels = {
    checking: locale === "zh" ? "检查运行状态" : "Checking status",
    healthy: locale === "zh" ? "系统运行正常" : "System healthy",
    degraded: locale === "zh" ? "部分数据待恢复" : "Data pipeline degraded",
    unavailable: locale === "zh" ? "服务连接异常" : "Service unavailable",
  };
  return <span className="inline-flex items-center gap-1.5 text-xs text-tm-muted">
    <span aria-hidden="true" className={`h-1.5 w-1.5 ${TONES[state]}`} />
    <span role="status">{labels[state]}</span>
  </span>;
}
