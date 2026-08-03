"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Inbox,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { ApiException } from "@/lib/api/client";
import {
  fetchAlertInbox,
  setAlertState,
  type AlertInboxItem,
  type AlertInboxResponse,
  type AlertWorkflowStatus,
} from "@/lib/api/alertsFeed";
import {
  alertTypeLabel,
  changeSummary,
  evidenceRows,
  impactSummary,
  queueFor,
  relevanceLabel,
  relativeTime,
  severityLabel,
  type AlertQueue,
} from "./alertPresentation";

const QUEUES: Array<{
  id: AlertQueue;
  icon: typeof Inbox;
}> = [
  { id: "needs_action", icon: ShieldAlert },
  { id: "watch", icon: BellRing },
  { id: "record", icon: Inbox },
  { id: "resolved", icon: CheckCircle2 },
];

const SEVERITY_CLASS = {
  critical: "border-tm-neg text-tm-neg",
  warning: "border-tm-warn text-tm-warn",
  info: "border-sky-500/70 text-sky-400",
};

function queueLabel(queue: AlertQueue, zh: boolean): string {
  return {
    needs_action: zh ? "需处理" : "Needs action",
    watch: zh ? "关注" : "Watch",
    record: zh ? "仅记录" : "Record only",
    resolved: zh ? "已处理" : "Resolved",
  }[queue];
}

function queueCount(data: AlertInboxResponse | null, queue: AlertQueue): number {
  if (!data) return 0;
  return data.alerts.filter((item) => queueFor(item) === queue).length;
}

function replaceState(
  data: AlertInboxResponse,
  alertId: number,
  status: AlertWorkflowStatus,
  snoozeUntil: string | null,
): AlertInboxResponse {
  return {
    ...data,
    alerts: data.alerts.map((item) =>
      item.id === alertId
        ? {
            ...item,
            state: {
              ...item.state,
              status,
              snooze_until: snoozeUntil,
              resolved_at: status === "resolved" ? new Date().toISOString() : null,
              updated_at: new Date().toISOString(),
            },
          }
        : item,
    ),
  };
}

export default function AlertWorkbench() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const { toast } = useToast();
  const [data, setData] = useState<AlertInboxResponse | null>(null);
  const [queue, setQueue] = useState<AlertQueue>("needs_action");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setAuthRequired(false);
    try {
      const next = await fetchAlertInbox(50);
      setData(next);
      const first = next.alerts.find((item) => queueFor(item) === "needs_action")
        ?? next.alerts.find((item) => item.state.status !== "resolved")
        ?? next.alerts[0];
      setSelectedId((current) =>
        current && next.alerts.some((item) => item.id === current)
          ? current
          : first?.id ?? null,
      );
    } catch (cause) {
      if (cause instanceof ApiException && cause.status === 401) {
        setAuthRequired(true);
        return;
      }
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () => data?.alerts.filter((item) => queueFor(item) === queue) ?? [],
    [data, queue],
  );
  const selected = data?.alerts.find((item) => item.id === selectedId) ?? visible[0] ?? null;

  useEffect(() => {
    if (visible.length > 0 && !visible.some((item) => item.id === selectedId)) {
      setSelectedId(visible[0].id);
    }
  }, [selectedId, visible]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, button, a")) return;
      if ((event.key !== "j" && event.key !== "k") || visible.length === 0) return;
      event.preventDefault();
      const index = Math.max(0, visible.findIndex((item) => item.id === selectedId));
      const nextIndex = event.key === "j"
        ? Math.min(visible.length - 1, index + 1)
        : Math.max(0, index - 1);
      setSelectedId(visible[nextIndex].id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId, visible]);

  async function persistState(
    item: AlertInboxItem,
    status: AlertWorkflowStatus,
    snoozeUntil: string | null = null,
    withUndo = true,
  ) {
    if (!data) return;
    const previous = item.state;
    setBusyId(item.id);
    setData((current) => current ? replaceState(current, item.id, status, snoozeUntil) : current);
    try {
      await setAlertState(item.id, {
        status,
        snooze_until: snoozeUntil,
      });
      if (withUndo && status !== "open") {
        toast.success(
          status === "resolved"
            ? (zh ? "已标记为已处理" : "Marked resolved")
            : (zh ? "已稍后提醒" : "Snoozed"),
          {
            duration: 8000,
            action: {
              label: zh ? "撤销" : "Undo",
              onClick: () => {
                void persistState(item, previous.status, previous.snooze_until, false);
              },
            },
          },
        );
      }
    } catch (cause) {
      setData((current) => current ? replaceState(current, item.id, previous.status, previous.snooze_until) : current);
      toast.error(
        zh
          ? `状态保存失败：${cause instanceof Error ? cause.message : String(cause)}`
          : `Failed to save state: ${cause instanceof Error ? cause.message : String(cause)}`,
      );
    } finally {
      setBusyId(null);
    }
  }

  const sourceFresh = data?.source_status === "fresh";
  const needsAction = queueCount(data, "needs_action");
  const positionCount = data?.alerts.filter(
    (item) => queueFor(item) === "needs_action" && item.relevance === "position",
  ).length ?? 0;
  const recommendationCount = data?.alerts.filter(
    (item) => queueFor(item) === "needs_action" && item.relevance === "recommendation",
  ).length ?? 0;

  return (
    <div className="flex min-h-[calc(100vh-36px)] flex-col bg-tm-bg font-tm-mono text-tm-fg">
      <header className="flex min-h-14 items-center justify-between border-b border-tm-rule px-4 py-2">
        <div>
          <h1 className="text-[16px] font-semibold tracking-tight">
            {zh ? "警报" : "Alerts"} <span className="font-normal text-tm-fg-2">Alerts</span>
          </h1>
          <p className="mt-0.5 text-[10px] text-tm-muted">
            {zh ? "只处理会改变决策的信息" : "Only handle information that can change a decision"}
          </p>
        </div>
        <div className="flex items-center gap-5 text-[10px] text-tm-muted">
          <span className={sourceFresh ? "text-tm-pos" : "text-tm-warn"}>
            {sourceFresh ? "●" : "▲"} {zh ? "数据源" : "Feed"} {sourceFresh ? (zh ? "正常" : "healthy") : (zh ? "待检查" : "check")}
          </span>
          <span>{data?.as_of ? new Date(data.as_of).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" }) : "--:--"}</span>
          <span className={needsAction > 0 ? "text-tm-neg" : "text-tm-pos"}>
            {needsAction} {zh ? "条需处理" : "need action"}
          </span>
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1 border border-tm-rule px-2 py-1 text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent">
            <RefreshCw className="h-3 w-3" /> {zh ? "刷新" : "Refresh"}
          </button>
        </div>
      </header>

      <section className="mx-3 mt-3 flex items-center gap-3 border border-tm-rule bg-tm-bg-2 px-3 py-2.5">
        <AlertTriangle className={needsAction > 0 ? "h-5 w-5 text-tm-warn" : "h-5 w-5 text-tm-pos"} />
        <p className="flex-1 text-[12px]">
          {zh
            ? `今天有 ${needsAction} 条关键变化，${positionCount} 条影响当前持仓，${recommendationCount} 条影响今日候选。`
            : `${needsAction} key changes today, ${positionCount} affect positions and ${recommendationCount} affect today's picks.`}
        </p>
        <Link href="/methodology#alerts" className="border border-tm-rule px-2.5 py-1.5 text-[10px] text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent">
          {zh ? "规则与阈值" : "Rules & thresholds"}
        </Link>
      </section>

      {authRequired ? (
        <div className="m-3 flex flex-1 items-center justify-center border border-tm-rule bg-tm-bg-2">
          <div className="max-w-md text-center">
            <ShieldAlert className="mx-auto h-7 w-7 text-tm-muted" />
            <h2 className="mt-3 text-sm">{zh ? "登录后启用决策分诊" : "Sign in for decision triage"}</h2>
            <p className="mt-2 text-[11px] leading-5 text-tm-muted">
              {zh ? "持仓、今日候选、关注列表与处理状态都属于你的账户上下文。" : "Positions, picks, watchlists, and triage state belong to your account context."}
            </p>
            <Link href="/login" className="mt-4 inline-block border border-tm-accent px-3 py-1.5 text-[11px] text-tm-accent hover:bg-tm-accent hover:text-tm-bg">
              {zh ? "前往登录" : "Sign in"}
            </Link>
          </div>
        </div>
      ) : error ? (
        <div role="alert" className="m-3 flex flex-1 items-center justify-center border border-tm-neg/50 bg-tm-neg/5 p-5 text-center">
          <div>
            <p className="text-sm text-tm-neg">{zh ? "警报队列加载失败" : "Alert queue failed to load"}</p>
            <p className="mt-2 max-w-xl text-[10px] text-tm-muted">{error}</p>
            <button type="button" onClick={() => void load()} className="mt-4 border border-tm-neg px-3 py-1.5 text-[10px] text-tm-neg">
              {zh ? "重试" : "Retry"}
            </button>
          </div>
        </div>
      ) : !data ? (
        <div className="m-3 flex flex-1 items-center justify-center border border-tm-rule bg-tm-bg-2 text-[11px] text-tm-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          {zh ? "正在建立决策上下文…" : "Building decision context…"}
        </div>
      ) : (
        <div className="m-3 grid flex-1 grid-cols-[190px_minmax(520px,1fr)_360px] overflow-hidden border border-tm-rule">
          <aside className="border-r border-tm-rule bg-tm-bg-2/50 p-2">
            <p className="px-2 py-1 text-[9px] uppercase tracking-[0.12em] text-tm-muted">
              {zh ? "队列导航" : "Queue navigation"}
            </p>
            <nav className="mt-1 space-y-1">
              {QUEUES.map(({ id, icon: Icon }) => {
                const active = queue === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setQueue(id)}
                    className={`flex w-full items-center gap-2 border-l-2 px-2 py-2 text-left text-[11px] ${active ? "border-tm-accent bg-tm-accent/10 text-tm-accent" : "border-transparent text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span className="flex-1">{queueLabel(id, zh)}</span>
                    <span className="border border-tm-rule px-1.5 py-0.5 text-[9px]">{queueCount(data, id)}</span>
                  </button>
                );
              })}
            </nav>

            <div className="mt-5 border-t border-tm-rule pt-3">
              <p className="px-2 text-[9px] uppercase tracking-[0.12em] text-tm-muted">
                {zh ? "排序依据" : "Ranking"}
              </p>
              <div className="mt-2 space-y-1.5 px-2 text-[9.5px] leading-4 text-tm-muted">
                <p>{zh ? "决策相关性 0–40" : "Decision relevance 0–40"}</p>
                <p>{zh ? "严重性 0–25" : "Severity 0–25"}</p>
                <p>{zh ? "新鲜度 0–20" : "Freshness 0–20"}</p>
                <p>{zh ? "证据置信度 0–15" : "Evidence confidence 0–15"}</p>
              </div>
            </div>

            <div className="mt-5 border-t border-tm-rule px-2 pt-3 text-[9px] leading-4 text-tm-muted">
              <p>J / K {zh ? "上下选择" : "move selection"}</p>
              <p>{zh ? "所有处理动作保留撤销窗口" : "All triage actions support undo"}</p>
            </div>
          </aside>

          <main className="min-w-0 border-r border-tm-rule">
            <div className="flex h-9 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-3 text-[10px]">
              <span className="text-tm-fg-2">{queueLabel(queue, zh)}</span>
              <span className="text-tm-muted">
                {zh ? "按决策优先级排序" : "Ranked by decision priority"} · {visible.length}
              </span>
            </div>
            {visible.length === 0 ? (
              <div className="flex h-full min-h-80 items-center justify-center text-center text-[11px] text-tm-muted">
                <div>
                  <CheckCircle2 className="mx-auto mb-2 h-5 w-5 text-tm-pos" />
                  {queue === "needs_action"
                    ? (zh ? "当前没有需要立即处理的警报。" : "Nothing needs immediate action.")
                    : (zh ? "这个队列目前为空。" : "This queue is empty.")}
                </div>
              </div>
            ) : (
              <div className="divide-y divide-tm-rule overflow-y-auto">
                {visible.map((item) => {
                  const active = selected?.id === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className={`grid w-full grid-cols-[82px_92px_minmax(180px,1.1fr)_minmax(190px,1fr)_92px] gap-2 border-l-2 px-3 py-3 text-left transition-colors ${active ? "border-tm-accent bg-tm-accent/5" : item.severity === "critical" ? "border-tm-neg hover:bg-tm-bg-2" : item.severity === "warning" ? "border-tm-warn hover:bg-tm-bg-2" : "border-sky-500/60 hover:bg-tm-bg-2"}`}
                    >
                      <div>
                        <span className={`inline-block border px-1.5 py-0.5 text-[9px] ${SEVERITY_CLASS[item.severity]}`}>
                          {severityLabel(item.severity, locale)}
                        </span>
                        <p className="mt-2 text-[9px] text-tm-muted">{relativeTime(item.created_at, locale)}</p>
                        {item.state.status === "snoozed" ? (
                          <p className="mt-1 text-[9px] text-tm-warn">{zh ? "已暂缓" : "Snoozed"}</p>
                        ) : null}
                      </div>
                      <div>
                        <p className="font-mono text-[18px] font-semibold">{item.ticker}</p>
                        <p className="mt-1 text-[9px] text-tm-muted">{alertTypeLabel(item, locale)}</p>
                      </div>
                      <div>
                        <p className="text-[11px] leading-4 text-tm-fg">{changeSummary(item, locale)}</p>
                        <p className="mt-1 text-[9.5px] text-tm-accent">{zh ? "查看变化详情" : "View change details"}</p>
                      </div>
                      <div>
                        <p className="text-[10px] leading-4 text-tm-fg-2">{impactSummary(item, locale)}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-mono text-[16px] text-tm-fg">{item.triage_score}</p>
                        <p className="text-[9px] text-tm-muted">{relevanceLabel(item.relevance, locale)}</p>
                        <p className="mt-1 text-[9px] text-tm-muted">{item.source_count} {zh ? "个来源" : "source(s)"}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </main>

          <aside className="min-w-0 bg-tm-bg-2/20">
            {!selected ? (
              <div className="flex h-full items-center justify-center p-6 text-center text-[10px] text-tm-muted">
                {zh ? "选择一条警报查看证据和关联对象。" : "Select an alert to inspect its evidence and linked objects."}
              </div>
            ) : (
              <div className="h-full overflow-y-auto">
                <div className="flex h-9 items-center justify-between border-b border-tm-rule px-3 text-[10px]">
                  <span>{zh ? "所选警报" : "Selected alert"} · {selected.ticker}</span>
                  <span className={SEVERITY_CLASS[selected.severity].split(" ")[1]}>
                    {severityLabel(selected.severity, locale)}
                  </span>
                </div>

                <section className="border-b border-tm-rule p-3">
                  <h2 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "变化证据" : "Change evidence"}
                  </h2>
                  <p className="mt-2 text-[12px] leading-5">{changeSummary(selected, locale)}</p>
                  <div className="mt-3 divide-y divide-tm-rule border border-tm-rule">
                    {evidenceRows(selected).length > 0 ? evidenceRows(selected).map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between px-2 py-1.5 text-[9.5px]">
                        <span className="text-tm-muted">{key}</span>
                        <span className="max-w-[190px] truncate font-mono text-tm-fg-2" title={value}>{value}</span>
                      </div>
                    )) : (
                      <p className="px-2 py-2 text-[9.5px] text-tm-muted">
                        {zh ? "当前事件没有更多结构化字段。" : "No additional structured facts are available."}
                      </p>
                    )}
                  </div>
                  <p className="mt-2 text-[9px] leading-4 text-tm-muted">
                    {zh ? "事件与指标同期发生，仅作相关性线索，不推断因果。" : "Events and metrics are contemporaneous evidence only; no causal claim is inferred."}
                  </p>
                </section>

                <section className="border-b border-tm-rule p-3">
                  <h2 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "决策影响" : "Decision impact"}
                  </h2>
                  <p className="mt-2 text-[10px] leading-4 text-tm-fg-2">{impactSummary(selected, locale)}</p>
                  <div className="mt-3 grid grid-cols-2 gap-px bg-tm-rule border border-tm-rule text-[9.5px]">
                    <div className="bg-tm-bg px-2 py-2">
                      <p className="text-tm-muted">{zh ? "关联对象" : "Linked object"}</p>
                      <p className="mt-1 text-tm-fg">{relevanceLabel(selected.relevance, locale)}</p>
                    </div>
                    <div className="bg-tm-bg px-2 py-2">
                      <p className="text-tm-muted">{zh ? "分诊分数" : "Triage score"}</p>
                      <p className="mt-1 font-mono text-tm-fg">{selected.triage_score}/100</p>
                    </div>
                    <div className="bg-tm-bg px-2 py-2">
                      <p className="text-tm-muted">{zh ? "置信等级" : "Confidence"}</p>
                      <p className="mt-1 text-tm-fg">{selected.confidence}</p>
                    </div>
                    <div className="bg-tm-bg px-2 py-2">
                      <p className="text-tm-muted">{zh ? "推荐来源" : "Recommendation"}</p>
                      <p className="mt-1 text-tm-fg">
                        {selected.context.recommendation_run_id
                          ? `RUN #${selected.context.recommendation_run_id}`
                          : (zh ? "未关联" : "Not linked")}
                      </p>
                    </div>
                  </div>
                  <div className="mt-2 flex gap-2 text-[9px]">
                    {selected.context.in_position ? (
                      <Link href="/paper" className="text-tm-accent hover:underline">
                        {zh ? "打开当前持仓" : "Open position"} ↗
                      </Link>
                    ) : null}
                    {selected.context.in_recommendation ? (
                      <Link href="/picks" className="text-tm-accent hover:underline">
                        {zh ? "打开今日推荐" : "Open picks"} ↗
                      </Link>
                    ) : null}
                  </div>
                </section>

                <section className="p-3">
                  <h2 className="text-[10px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "建议动作" : "Suggested action"}
                  </h2>
                  <p className="mt-2 text-[9.5px] leading-4 text-tm-muted">
                    {zh ? "先查看标的上下文，再决定是否关闭该事项。系统不会自动交易。" : "Review the ticker context before resolving. The system never trades automatically."}
                  </p>
                  <Link
                    href={`/stock/${selected.ticker}#news`}
                    className="mt-3 flex w-full items-center justify-center gap-2 bg-tm-accent px-3 py-2 text-[11px] font-semibold text-tm-bg hover:brightness-110"
                  >
                    {zh ? "审查并处理" : "Review and process"}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      disabled={busyId === selected.id}
                      onClick={() => void persistState(selected, "snoozed", new Date(Date.now() + 4 * 3600_000).toISOString())}
                      className="flex items-center justify-center gap-1.5 border border-tm-rule px-2 py-1.5 text-[10px] text-tm-fg-2 hover:border-tm-warn hover:text-tm-warn disabled:opacity-50"
                    >
                      <Clock3 className="h-3 w-3" /> {zh ? "4 小时后提醒" : "Snooze 4h"}
                    </button>
                    <button
                      type="button"
                      disabled={busyId === selected.id || selected.state.status === "resolved"}
                      onClick={() => void persistState(selected, "resolved")}
                      className="flex items-center justify-center gap-1.5 border border-tm-rule px-2 py-1.5 text-[10px] text-tm-fg-2 hover:border-tm-pos hover:text-tm-pos disabled:opacity-50"
                    >
                      {busyId === selected.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                      {zh ? "标记已处理" : "Mark resolved"}
                    </button>
                  </div>
                </section>
              </div>
            )}
          </aside>
        </div>
      )}

      <footer className="flex min-h-7 items-center justify-between border-t border-tm-rule px-3 text-[9px] text-tm-muted">
        <span>{zh ? "数据仅供研究参考，不构成投资建议，也不代表系统可执行任何交易。" : "Research only. Not investment advice and not an automated trading instruction."}</span>
        <span>{zh ? "排序可解释，可撤销，有审计记录" : "Explainable ranking · reversible · auditable"}</span>
      </footer>
    </div>
  );
}
