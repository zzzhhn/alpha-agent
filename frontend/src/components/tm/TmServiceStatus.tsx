import { type Locale } from "@/lib/i18n";

export type ServiceState = "checking" | "healthy" | "degraded" | "partial" | "unknown" | "unavailable";
const TONES: Record<ServiceState, string> = {
  checking: "bg-tm-muted", healthy: "bg-tm-pos", degraded: "bg-tm-warn", unavailable: "bg-tm-neg",
  partial: "bg-tm-warn", unknown: "bg-tm-muted",
};

export function TmServiceStatus({ state, locale }: { state: ServiceState; locale: Locale }) {
  const labels = {
    checking: locale === "zh" ? "检查运行状态" : "Checking status",
    healthy: locale === "zh" ? "系统运行正常" : "System healthy",
    degraded: locale === "zh" ? "部分数据待恢复" : "Data pipeline degraded",
    partial: locale === "zh" ? "服务可用，数据状态待确认" : "Service available · data status unknown",
    unknown: locale === "zh" ? "连接状态待确认" : "Connection status unconfirmed",
    unavailable: locale === "zh" ? "服务暂不可用" : "Service unavailable",
  };
  const hints: Record<ServiceState, string> = locale === "zh" ? {
    checking: "正在检查服务连接与数据更新状态。",
    healthy: "本次检查中，服务连接正常，关键数据任务满足更新要求。",
    degraded: "服务连接正常，但部分数据任务过期、未完成或失败。点击查看数据状态。",
    partial: "服务连接正常；数据检查暂未完成，不代表数据正常或服务宕机。页面可见时每分钟重试。",
    unknown: "连接检查超时、网络失败或返回无法确认的响应。尚不能判断服务是否故障，页面可见时每分钟重试。",
    unavailable: "服务检查返回服务端错误或数据库不可用。点击查看详情，页面可见时每分钟重试。",
  } : {
    checking: "Checking connectivity and pipeline freshness.",
    healthy: "This check confirmed connectivity and required pipeline updates.",
    degraded: "Service is reachable, but some data jobs are stale, incomplete or failed. Open data status for details.",
    partial: "Service is reachable; pipeline status could not be checked. Retried every minute while this tab is visible.",
    unknown: "A timeout, network error or inconclusive response prevented confirmation. Retried every minute while visible.",
    unavailable: "The service check returned a server error or an unavailable database. Open details; retried every minute while visible.",
  };
  return <span title={hints[state]} className="inline-flex items-center gap-1.5 text-xs text-tm-muted">
    <span aria-hidden="true" className={`h-1.5 w-1.5 ${TONES[state]}`} />
    <span role="status">{labels[state]}</span>
  </span>;
}
