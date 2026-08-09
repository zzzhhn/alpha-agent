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
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { DecisionStrip } from "@/components/workbench/DecisionStrip";
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

type SeverityFilter = "all" | AlertInboxItem["severity"];
type RelevanceFilter = "all" | AlertInboxItem["relevance"];
const SAVED_VIEW_KEY = "alphacore.alerts.saved-view.v1";

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
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [relevanceFilter, setRelevanceFilter] = useState<RelevanceFilter>("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [auditExpanded, setAuditExpanded] = useState(false);

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

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(SAVED_VIEW_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as { queue?: AlertQueue; severity?: SeverityFilter; relevance?: RelevanceFilter };
      if (saved.queue) setQueue(saved.queue);
      if (saved.severity) setSeverityFilter(saved.severity);
      if (saved.relevance) setRelevanceFilter(saved.relevance);
    } catch {
      // A malformed browser-local view must never block the real inbox.
    }
  }, []);

  const visible = useMemo(
    () => data?.alerts.filter((item) =>
      queueFor(item) === queue
      && (severityFilter === "all" || item.severity === severityFilter)
      && (relevanceFilter === "all" || item.relevance === relevanceFilter)
    ) ?? [],
    [data, queue, severityFilter, relevanceFilter],
  );
  const auditCandidates = useMemo(
    () => (data?.alerts ?? [])
      .filter((item) => item.state.updated_at)
      .sort((a, b) => (b.state.updated_at ?? "").localeCompare(a.state.updated_at ?? "")),
    [data],
  );
  const auditItems = useMemo(
    () => auditExpanded ? auditCandidates : auditCandidates.slice(0, 3),
    [auditCandidates, auditExpanded],
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

  function saveView() {
    try {
      window.localStorage.setItem(SAVED_VIEW_KEY, JSON.stringify({
        queue,
        severity: severityFilter,
        relevance: relevanceFilter,
      }));
      toast.success(zh ? "当前队列视图已保存到此浏览器" : "Queue view saved in this browser");
    } catch {
      toast.error(zh ? "浏览器未允许保存视图" : "The browser did not allow saving this view");
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
      <WorkbenchHeader
        eyebrow={zh ? "每日工作流" : "Daily workflow"}
        title={<>{zh ? "警报" : "Alerts"} <span className="font-normal text-tm-fg-2">Alerts</span></>}
        subtitle={zh ? "只处理会改变决策的信息" : "Only handle information that can change a decision"}
        statuses={[
          { label: zh ? "数据新鲜度" : "Data freshness", value: data?.as_of ? new Date(data.as_of).toLocaleTimeString(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" }) : "—", tone: sourceFresh ? "positive" : "warning" },
          { label: zh ? "抓取健康" : "Feed health", value: sourceFresh ? (zh ? "正常" : "HEALTHY") : (zh ? "待检查" : "CHECK"), tone: sourceFresh ? "positive" : "warning" },
          { label: zh ? "需要处理" : "Needs action", value: String(needsAction), tone: needsAction > 0 ? "negative" : "positive" },
        ]}
        action={(
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1 border border-tm-rule px-2 py-1 text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent">
            <RefreshCw className="h-3 w-3" /> {zh ? "刷新" : "Refresh"}
          </button>
        )}
      />

      <DecisionStrip
        headline={<span className="inline-flex items-center gap-3"><AlertTriangle className={needsAction > 0 ? "h-6 w-6 text-tm-warn" : "h-6 w-6 text-tm-pos"} />{zh ? `今天有 ${needsAction} 条关键变化` : `${needsAction} key changes today`}</span>}
        description={zh ? "按决策相关性排序，优先处理与持仓和今日候选相连的变化。" : "Ranked by decision relevance, prioritizing changes linked to positions and today's picks."}
        metrics={[
          { label: zh ? "影响持仓" : "Positions", value: positionCount, tone: positionCount > 0 ? "warning" : "default" },
          { label: zh ? "影响候选" : "Picks", value: recommendationCount, tone: recommendationCount > 0 ? "warning" : "default" },
          { label: zh ? "队列总数" : "Queue total", value: data?.alerts.length ?? 0 },
        ]}
        action={<Link href="/methodology#alerts" className="border border-tm-rule px-3 py-2 text-[10px] text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent">{zh ? "规则与阈值" : "Rules & thresholds"}</Link>}
      />

      <div className="flex flex-1 flex-col">
        <div className="mx-6 mt-4 grid min-h-[600px] grid-cols-1 overflow-hidden border border-tm-rule min-[1280px]:grid-cols-[0.9fr_2.2fr_1.25fr]">
          <aside className="border-r border-tm-rule bg-tm-bg-2/50 p-3">
            <p className="px-2 py-1 text-[10px] uppercase tracking-[0.12em] text-tm-muted">
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
                    className={`flex min-h-10 w-full items-center gap-2 border-l-2 px-3 py-2 text-left text-[12px] ${active ? "border-tm-accent bg-tm-accent/10 text-tm-accent" : "border-transparent text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span className="flex-1">{queueLabel(id, zh)}</span>
                    <span className="border border-tm-rule px-1.5 py-0.5 text-[9px]">{queueCount(data, id)}</span>
                  </button>
                );
              })}
            </nav>

            <div className="mt-5 border-t border-tm-rule pt-3">
              <p className="px-2 text-[10px] uppercase tracking-[0.12em] text-tm-muted">
                {zh ? "严重性" : "Severity"}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-1 px-2">
                {(["all", "critical", "warning", "info"] as SeverityFilter[]).map((value) => (
                  <button key={value} type="button" onClick={() => setSeverityFilter(value)} className={`border px-2 py-1.5 text-left text-[10px] ${severityFilter === value ? "border-tm-accent text-tm-accent" : "border-tm-rule text-tm-muted hover:text-tm-fg"}`}>
                    {value === "all" ? (zh ? "全部" : "All") : severityLabel(value, locale)}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 border-t border-tm-rule pt-3">
              <p className="px-2 text-[10px] uppercase tracking-[0.12em] text-tm-muted">{zh ? "关联对象" : "Relevance"}</p>
              <div className="mt-2 space-y-1 px-2">
                {(["all", "position", "recommendation", "watchlist", "market", "record"] as RelevanceFilter[]).map((value) => (
                  <button key={value} type="button" onClick={() => setRelevanceFilter(value)} className={`flex w-full justify-between border-l-2 px-2 py-1.5 text-[10px] ${relevanceFilter === value ? "border-tm-accent bg-tm-accent/5 text-tm-accent" : "border-transparent text-tm-muted hover:text-tm-fg"}`}>
                    <span>{value === "all" ? (zh ? "全部关联" : "All relevance") : relevanceLabel(value, locale)}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 border-t border-tm-rule px-2 pt-3 text-[9.5px] leading-5 text-tm-muted">
              <p>{zh ? "排序：相关性 × 严重性 × 新鲜度 × 置信度" : "Rank: relevance × severity × freshness × confidence"}</p>
              <p className="mt-2">J / K {zh ? "上下选择" : "move selection"}</p>
              <p>{zh ? "所有处理动作保留撤销窗口" : "All triage actions support undo"}</p>
              <button type="button" onClick={saveView} className="mt-3 w-full border border-tm-rule px-2 py-2 text-[10px] text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent">
                {zh ? "保存当前视图" : "Save current view"}
              </button>
              <p className="mt-1 text-[8.5px]">{zh ? "筛选配置仅保存在当前浏览器" : "Filters are browser-local"}</p>
            </div>
          </aside>

          <main className="min-w-0 border-r border-tm-rule">
            <div className="flex h-11 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4 text-[11px]">
              <span className="text-tm-fg-2">{queueLabel(queue, zh)} · {visible.length}</span>
              <span className="text-tm-muted">
                {zh ? "按决策优先级排序" : "Ranked by decision priority"}
              </span>
            </div>
            <div className="grid h-9 grid-cols-[68px_88px_minmax(150px,1.2fr)_minmax(130px,1fr)_84px] items-center gap-2 border-b border-tm-rule bg-tm-bg px-4 text-[9px] uppercase tracking-[0.08em] text-tm-muted">
              <span>{zh ? "严重性／时间" : "Severity / time"}</span>
              <span>{zh ? "标的／来源" : "Ticker / source"}</span>
              <span>{zh ? "变化／证据" : "Change / evidence"}</span>
              <span>{zh ? "影响暴露" : "Affected exposure"}</span>
              <span className="text-right">{zh ? "处置" : "Disposition"}</span>
            </div>
            {error && data ? (
              <div role="alert" className="flex items-center justify-between gap-3 border-b border-tm-neg/50 bg-tm-neg/5 px-4 py-2 text-[10px]">
                <span className="text-tm-neg">{zh ? "刷新失败，显示上次可用队列。" : "Refresh failed; showing the last available queue."}</span>
                <button type="button" onClick={() => void load()} className="shrink-0 border border-tm-neg px-2 py-1 text-[9px] text-tm-neg hover:bg-tm-neg/10">
                  {zh ? "重试" : "Retry"}
                </button>
              </div>
            ) : null}
            {authRequired ? (
              <div className="flex min-h-[360px] items-center justify-center border-b border-tm-rule bg-tm-bg-2/30 p-6 text-center">
                <div className="max-w-md">
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
            ) : !data ? (
              <div role={error ? "alert" : undefined} className={`flex min-h-[360px] items-center justify-center p-6 text-center ${error ? "border-b border-tm-neg/50 bg-tm-neg/5" : "bg-tm-bg-2/20"}`}>
                <div>
                  <p className={`text-sm ${error ? "text-tm-neg" : "text-tm-muted"}`}>
                    {error ? (zh ? "警报队列加载失败" : "Alert queue failed to load") : (
                      <span className="inline-flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {zh ? "正在建立决策上下文…" : "Building decision context…"}
                      </span>
                    )}
                  </p>
                  {error ? <p className="mt-2 max-w-xl text-[10px] text-tm-muted">{error}</p> : null}
                  {error ? (
                    <button type="button" onClick={() => void load()} className="mt-4 border border-tm-neg px-3 py-1.5 text-[10px] text-tm-neg hover:bg-tm-neg/10">
                      {zh ? "重试" : "Retry"}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : visible.length === 0 ? (
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
                      className={`grid min-h-[126px] w-full grid-cols-[68px_88px_minmax(150px,1.2fr)_minmax(130px,1fr)_84px] items-start gap-2 border-l-2 px-4 py-4 text-left transition-colors ${active ? "border-tm-accent bg-tm-accent/5 ring-1 ring-inset ring-tm-accent/30" : item.severity === "critical" ? "border-tm-neg hover:bg-tm-bg-2" : item.severity === "warning" ? "border-tm-warn hover:bg-tm-bg-2" : "border-sky-500/60 hover:bg-tm-bg-2"}`}
                    >
                      <div>
                        <span className={`inline-block border px-2 py-1 text-[10px] ${SEVERITY_CLASS[item.severity]}`}>
                          {severityLabel(item.severity, locale)}
                        </span>
                        <p className="mt-3 text-[10px] text-tm-muted">{relativeTime(item.created_at, locale)}</p>
                        {item.state.status === "snoozed" ? (
                          <p className="mt-1 text-[9px] text-tm-warn">{zh ? "已暂缓" : "Snoozed"}</p>
                        ) : null}
                      </div>
                      <div>
                        <p className="font-mono text-[20px] font-semibold">{item.ticker}</p>
                        <p className="mt-2 text-[10px] text-tm-muted">{alertTypeLabel(item, locale)}</p>
                        <p className="mt-1 text-[9px] text-tm-muted">{item.source_count} {zh ? "个来源" : "source(s)"}</p>
                      </div>
                      <div>
                        <p className="text-[12px] leading-5 text-tm-fg">{changeSummary(item, locale)}</p>
                        <p className="mt-2 text-[10px] text-tm-fg-2">
                          {zh ? "证据强度" : "Evidence"}: <span className="text-tm-accent">{item.confidence}</span>
                          <span className="ml-2 text-tm-muted">{item.confidence_score}/100</span>
                        </p>
                        <p className="mt-1 text-[9px] text-tm-accent">{zh ? "查看变化详情 →" : "View change details →"}</p>
                      </div>
                      <div>
                        <p className="text-[11px] leading-5 text-tm-fg-2">{impactSummary(item, locale)}</p>
                        <p className="mt-2 text-[10px] text-tm-muted">{relevanceLabel(item.relevance, locale)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-[10px] text-tm-fg-2">
                          {item.state.status === "resolved" ? (zh ? "已处理" : "Resolved") : item.state.status === "snoozed" ? (zh ? "已暂缓" : "Snoozed") : (zh ? "待处理" : "Open")}
                        </p>
                        <p className="mt-2 font-mono text-[17px] text-tm-fg">{item.triage_score}</p>
                        <p className="mt-1 text-[9px] text-tm-muted">{zh ? "分诊分数" : "Triage"}</p>
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
                <div className="flex h-11 items-center justify-between border-b border-tm-rule px-4 text-[11px]">
                  <span>{zh ? "所选警报" : "Selected alert"} · {selected.ticker}</span>
                  <span className={SEVERITY_CLASS[selected.severity].split(" ")[1]}>
                    {severityLabel(selected.severity, locale)}
                  </span>
                </div>

                <section className="border-b border-r border-tm-rule p-4 min-[1680px]:border-r-0">
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "变化证据" : "Change evidence"}
                  </h2>
                  <p className="mt-2 text-[14px] leading-6">{changeSummary(selected, locale)}</p>
                  <div className="mt-4 border border-tm-rule bg-tm-bg px-3 py-3">
                    <p className="text-[9px] uppercase tracking-[0.1em] text-tm-muted">{zh ? "证据时间窗" : "Evidence window"}</p>
                    <div className="relative mt-3 flex items-start justify-between before:absolute before:left-2 before:right-2 before:top-1.5 before:h-px before:bg-tm-rule">
                      {[
                        [zh ? "事件产生" : "Event", selected.created_at],
                        [zh ? "完成分诊" : "Triaged", selected.state.updated_at ?? selected.created_at],
                        [zh ? "数据截止" : "As of", data?.as_of],
                      ].map(([label, stamp], index) => (
                        <div key={`${label}-${index}`} className="relative z-10 w-1/3 text-center">
                          <span className={`mx-auto block h-3 w-3 rounded-full border ${index === 0 ? "border-tm-warn bg-tm-warn" : index === 2 ? "border-tm-accent bg-tm-accent" : "border-tm-rule bg-tm-bg"}`} />
                          <p className="mt-2 text-[9px] text-tm-fg-2">{label}</p>
                          <p className="mt-0.5 text-[8.5px] text-tm-muted">{stamp ? new Date(stamp).toLocaleTimeString(zh ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" }) : "—"}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-3 divide-y divide-tm-rule border border-tm-rule">
                    {evidenceRows(selected).length > 0 ? evidenceRows(selected).map(([key, value]) => (
                      <div key={key} className="flex min-h-8 items-center justify-between px-3 py-1.5 text-[10px]">
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

                <section className="border-b border-r border-tm-rule p-4 min-[1680px]:border-r-0">
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "决策影响" : "Decision impact"}
                  </h2>
                  <p className="mt-2 text-[11px] leading-5 text-tm-fg-2">{impactSummary(selected, locale)}</p>
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

                <section className="p-4">
                  <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "建议动作" : "Suggested action"}
                  </h2>
                  <p className="mt-2 text-[9.5px] leading-4 text-tm-muted">
                    {zh ? "先查看标的上下文，再决定是否关闭该事项。系统不会自动交易。" : "Review the ticker context before resolving. The system never trades automatically."}
                  </p>
                  <button
                    type="button"
                    disabled={busyId === selected.id}
                    onClick={() => void persistState(selected, selected.state.status === "resolved" ? "open" : "resolved")}
                    className="mt-4 flex h-11 w-full items-center justify-center gap-2 bg-tm-accent px-3 text-[12px] font-semibold text-tm-bg hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
                  >
                    {busyId === selected.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    {selected.state.status === "resolved"
                      ? (zh ? "重新打开" : "Reopen alert")
                      : (zh ? "标记已处理" : "Mark resolved")}
                  </button>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      disabled={busyId === selected.id}
                      onClick={() => void persistState(selected, "snoozed", new Date(Date.now() + 4 * 3600_000).toISOString())}
                      className="flex items-center justify-center gap-1.5 border border-tm-rule px-2 py-1.5 text-[10px] text-tm-fg-2 hover:border-tm-warn hover:text-tm-warn disabled:opacity-50"
                    >
                      <Clock3 className="h-3 w-3" /> {zh ? "4 小时后提醒" : "Snooze 4h"}
                    </button>
                    <Link
                      href={`/stock/${selected.ticker}#news`}
                      className="flex items-center justify-center gap-1.5 border border-tm-rule px-2 py-1.5 text-[10px] text-tm-fg-2 hover:border-tm-accent hover:text-tm-accent"
                    >
                      <ExternalLink className="h-3 w-3" /> {zh ? "打开研究" : "Open research"}
                    </Link>
                  </div>
                  <div className="mt-4 border-t border-tm-rule pt-3 text-[9px] leading-5 text-tm-muted">
                    <p>{zh ? "当前状态" : "Current state"}: <span className="text-tm-fg-2">{selected.state.status}</span></p>
                    <p>{zh ? "最近更新" : "Last update"}: {selected.state.updated_at ? new Date(selected.state.updated_at).toLocaleString(zh ? "zh-CN" : "en-US") : (zh ? "尚无处理记录" : "No triage action yet")}</p>
                    <p>{zh ? "操作人" : "Actor"}: {zh ? "当前登录用户" : "Current authenticated user"}</p>
                  </div>
                </section>
              </div>
            )}
          </aside>
        </div>
        <section className="mx-6 mb-4 border-x border-b border-tm-rule">
          <div className="flex min-h-8 items-center justify-between border-b border-tm-rule bg-tm-bg-2/40 px-4 text-[9px] uppercase tracking-[0.08em] text-tm-muted">
            <span>{zh ? "审计轨迹" : "Audit trail"}</span>
            {auditCandidates.length > 3 ? (
              <button
                type="button"
                aria-expanded={auditExpanded}
                onClick={() => setAuditExpanded((expanded) => !expanded)}
                className="text-tm-accent hover:underline"
              >
                {auditExpanded
                  ? (zh ? "收起" : "Show latest 3")
                  : (zh ? `查看全部（${auditCandidates.length}）` : `View all (${auditCandidates.length})`)}
              </button>
            ) : null}
          </div>
          <div className="grid h-9 grid-cols-[190px_100px_120px_minmax(0,1fr)_120px] items-center gap-3 border-b border-tm-rule bg-tm-bg-2/40 px-4 text-[9px] uppercase tracking-[0.08em] text-tm-muted">
            <span>{zh ? "处理时间" : "Action time"}</span>
            <span>{zh ? "标的" : "Ticker"}</span>
            <span>{zh ? "动作" : "Action"}</span>
            <span>{zh ? "状态说明" : "Status note"}</span>
            <span>{zh ? "可恢复" : "Recovery"}</span>
          </div>
          {auditItems.length > 0 ? auditItems.map((item) => (
            <div key={`audit-${item.id}`} className="grid min-h-9 grid-cols-[190px_100px_120px_minmax(0,1fr)_120px] items-center gap-3 border-b border-tm-rule px-4 text-[10px] last:border-b-0">
              <span className="text-tm-muted">{item.state.updated_at ? new Date(item.state.updated_at).toLocaleString(zh ? "zh-CN" : "en-US") : "—"}</span>
              <span className="font-mono text-tm-fg">{item.ticker}</span>
              <span className="text-tm-fg-2">{item.state.status === "resolved" ? (zh ? "标记已处理" : "Resolved") : (zh ? "稍后提醒" : "Snoozed")}</span>
              <span className="truncate text-tm-muted">{item.state.note ?? (zh ? "状态由当前账户更新" : "State updated by the current account")}</span>
              <span className="text-tm-accent">{zh ? "支持撤销" : "Undo available"}</span>
            </div>
          )) : (
            <div className="flex min-h-12 items-center px-4 text-[10px] text-tm-muted">
              {zh ? "当前没有处理记录。完成一次稍后提醒或标记处理后，记录会显示在这里。" : "No triage actions yet. Snooze or resolve an item to create an audit entry."}
            </div>
          )}
        </section>
        </div>

      <footer className="flex min-h-7 items-center justify-between border-t border-tm-rule px-3 text-[9px] text-tm-muted">
        <span>{zh ? "数据仅供研究参考，不构成投资建议，也不代表系统可执行任何交易。" : "Research only. Not investment advice and not an automated trading instruction."}</span>
        <span>{zh ? "排序可解释，可撤销，有审计记录" : "Explainable ranking · reversible · auditable"}</span>
      </footer>
    </div>
  );
}
