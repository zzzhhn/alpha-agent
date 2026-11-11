"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Inbox,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { DecisionStrip } from "@/components/workbench/DecisionStrip";
import { TmButton, TmDisclosureButton, TmLinkButton, TmRowButton } from "@/components/tm/TmButton";
import { TmInput, TmSelect } from "@/components/tm/TmField";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmScreen } from "@/components/tm/TmPane";
import { ApiException } from "@/lib/api/client";
import {
  fetchAlertInbox,
  setAlertState,
  setAlertStatesBatch,
  alertMemberIds,
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
  confidenceLabel,
  workflowLabel,
  selectedAlert,
  type AlertQueue,
} from "./alertPresentation";
import "./alerts-workbench.css";

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
  info: "border-tm-info text-tm-info",
};

type SeverityFilter = "all" | AlertInboxItem["severity"];
type RelevanceFilter = "all" | AlertInboxItem["relevance"];
const SAVED_VIEW_KEY = "alphacore.alerts.saved-view.v1";

function queueLabel(queue: AlertQueue, zh: boolean): string {
  return {
    needs_action: zh ? "需处理" : "To review",
    watch: zh ? "关注" : "Watch",
    record: zh ? "仅记录" : "Records",
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
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 5;
  const listScrollRef = useRef<HTMLDivElement>(null);
  const inspectorRef = useRef<HTMLElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
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
        setData(null);
        setAuthRequired(true);
        return;
      }
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
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
      && (!search.trim() || `${item.ticker} ${alertTypeLabel(item, locale)} ${changeSummary(item, locale)}`.toLowerCase().includes(search.trim().toLowerCase()))
    ) ?? [],
    [data, queue, severityFilter, relevanceFilter, search, locale],
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
  const currentPage = Math.min(page, Math.max(1, Math.ceil(visible.length / pageSize)));
  const pageItems = useMemo(() => visible.slice((currentPage - 1) * pageSize, currentPage * pageSize), [visible, currentPage]);
  const selected = selectedAlert(pageItems, selectedId);

  useEffect(() => {
    // Each new slice starts at its first row, without moving the page itself.
    listScrollRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [currentPage, queue, search, severityFilter, relevanceFilter]);

  useEffect(() => {
    inspectorRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [selected?.id]);

  useEffect(() => {
    setSelectedId(selected?.id ?? null);
  }, [selected?.id]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, a, [contenteditable=true]")) return;
      if (target?.closest("button") && !target.closest("[data-alert-row]")) return;
      if ((event.key !== "j" && event.key !== "k") || pageItems.length === 0) return;
      event.preventDefault();
      const index = Math.max(0, pageItems.findIndex((item) => item.id === selectedId));
      const nextIndex = event.key === "j"
        ? Math.min(pageItems.length - 1, index + 1)
        : Math.max(0, index - 1);
      setSelectedId(pageItems[nextIndex].id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId, pageItems]);

  async function persistState(
    item: AlertInboxItem,
    status: AlertWorkflowStatus,
    snoozeUntil: string | null = null,
    withUndo = true,
  ) {
    if (!data) return;
    const previous = item.state;
    const ids = alertMemberIds(item);
    setBusyId(item.id);
    setData((current) => current ? replaceState(current, item.id, status, snoozeUntil) : current);
    try {
      // A grouped item stands for every same-day repeat; one decision covers
      // all of them so an older open member cannot keep the group open.
      const saved = ids.length > 1
        ? (await setAlertStatesBatch({ alert_ids: ids, status, snooze_until: snoozeUntil })).states[String(item.id)]
        : await setAlertState(item.id, { status, snooze_until: snoozeUntil });
      setData(current => current ? {...current, alerts: current.alerts.map(row => row.id === item.id && saved ? {...row, state:saved} : row)} : current);
      if (withUndo && status !== "open") {
        toast.success(
          status === "resolved"
            ? (ids.length > 1 ? (zh ? `已处理本组 ${ids.length} 条` : `Resolved ${ids.length} grouped alerts`) : (zh ? "已标记为已处理" : "Marked resolved"))
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
      setData(current => current ? {...current, alerts: current.alerts.map(row => row.id === item.id ? {...row, state:previous} : row)} : current);
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

  const needsAction = queueCount(data, "needs_action");
  const positionCount = data?.alerts.filter(
    (item) => queueFor(item) === "needs_action" && item.relevance === "position",
  ).length ?? 0;
  const recommendationCount = data?.alerts.filter(
    (item) => queueFor(item) === "needs_action" && item.relevance === "recommendation",
  ).length ?? 0;
  const newest = data?.alerts.reduce<string | null>((latest, item) => !latest || item.created_at > latest ? item.created_at : latest, null);
  const hasFilters = severityFilter !== "all" || relevanceFilter !== "all" || !!search;
  const stamp = (value: string | null | undefined) => value ? new Date(value).toLocaleString(zh ? "zh-CN" : "en-US", {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"}) : "—";
  function clearFilters() { setSeverityFilter("all"); setRelevanceFilter("all"); setSearch(""); setPage(1); }

  return (
    <TmScreen className="alerts-workbench font-tm-mono text-tm-fg">
      <WorkbenchHeader
        eyebrow={zh ? "每日工作流" : "Daily workflow"}
        title={zh ? "警报" : "Alerts"}
        subtitle={zh ? "先看变化，再决定如何处理。" : "Review the change, then decide what to do."}
        statuses={[
          { label: zh ? "最新事件" : "Latest event", value: stamp(newest), tone: data?.source_status === "stale" ? "warning" : "default" },
          { label: zh ? "队列更新" : "Inbox fetched", value: stamp(data?.as_of) },
        ]}
        action={(
          <TmButton variant="secondary" loading={loading} loadingLabel={zh ? "刷新中" : "Refreshing"} onClick={() => void load()}>
            <RefreshCw className="h-3 w-3" /> {zh ? "刷新" : "Refresh"}
          </TmButton>
        )}
      />

      <DecisionStrip
        headline={<span className="inline-flex items-center gap-2"><AlertTriangle className={`h-5 w-5 ${needsAction > 0 ? "text-tm-warn" : "text-tm-muted"}`} />{data ? (zh ? `${needsAction} 条待复核` : `${needsAction} to review`) : (zh ? "正在读取警报" : "Loading alerts")}</span>}
        description={data?.source_status === "stale"
          ? (zh ? "最新事件已超过 24 小时，以下为历史记录，并非今日新增。" : "Latest event is over 24 hours old. These are historical records, not new alerts today.")
          : data?.source_status === "empty" ? (zh ? "尚无事件记录，不能据此判断没有风险。" : "No events recorded yet; this does not establish an absence of risk.")
          : (zh ? "先复核持仓与候选相关变化；警报不是交易指令。" : "Review changes linked to holdings and picks. Alerts are not trade instructions.")}
        metrics={[
          { label: zh ? "关联持仓" : "Holdings", value: data ? positionCount : "—" },
          { label: zh ? "关联候选" : "Picks", value: data ? recommendationCount : "—" },
          { label: zh ? "本次载入（最近 50 条内）" : "Loaded (latest 50)", value: data?.alerts.length ?? "—" },
        ]}
        action={<TmLinkButton href="/methodology#alerts" variant="secondary" size="md">{zh ? "规则与阈值" : "Rules & thresholds"}</TmLinkButton>}
      />

      <div className="alerts-body">
        <div className="alerts-grid">
          <aside className="alerts-filters border-r border-tm-rule bg-tm-bg-2 p-3" aria-label={zh ? "警报队列与筛选" : "Alert queues and filters"}>
            <p className="px-2 py-1 text-xs uppercase tracking-[0.12em] text-tm-muted">
              {zh ? "队列导航" : "Queues"}
            </p>
            <nav className="mt-1 space-y-1">
              {QUEUES.map(({ id, icon: Icon }) => {
                const active = queue === id;
                return (
                  <TmRowButton
                    key={id}
                    onClick={() => {setQueue(id);setPage(1);}}
                    aria-pressed={active}
                    className={`flex min-h-10 w-full items-center gap-2 border-l-2 px-3 py-2 text-left text-[12px] ${active ? "border-tm-accent bg-tm-accent/10 text-tm-accent" : "border-transparent text-tm-fg-2 hover:bg-tm-bg-2 hover:text-tm-fg"}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span className="flex-1">{queueLabel(id, zh)}</span>
                    <span className="min-w-7 text-right tabular-nums font-semibold">{data ? queueCount(data, id) : "—"}</span>
                  </TmRowButton>
                );
              })}
            </nav>

            <div className="mt-4 space-y-4 border-t border-tm-rule pt-4">
                <TmSelect
                  label={zh ? "严重性" : "Severity"}
                  value={severityFilter}
                  onChange={value => {setSeverityFilter(value as SeverityFilter);setPage(1);}}
                  options={(["all", "critical", "warning", "info"] as SeverityFilter[]).map((value) => ({
                    value,
                    label: value === "all" ? (zh ? "全部" : "All") : severityLabel(value, locale),
                  }))}
                />
                <TmSelect
                  label={zh ? "关联对象" : "Relevance"}
                  value={relevanceFilter}
                  onChange={value => {setRelevanceFilter(value as RelevanceFilter);setPage(1);}}
                  options={(["all", "position", "recommendation", "watchlist", "market", "record"] as RelevanceFilter[]).map((value) => ({
                    value,
                    label: value === "all" ? (zh ? "全部关联" : "All relevance") : relevanceLabel(value, locale),
                  }))}
                />
            </div>

            <div className="mt-5 border-t border-tm-rule px-2 pt-3 text-xs leading-5 text-tm-muted">
              {hasFilters ? <TmButton variant="ghost" size="sm" onClick={clearFilters} className="w-full">{zh ? "清除筛选" : "Clear filters"}</TmButton> : null}
              <TmButton variant="secondary" size="sm" onClick={saveView} className="mt-3 w-full">
                {zh ? "保存当前视图" : "Save view"}
              </TmButton>
              <p className="mt-2">{zh ? "仅保存到此浏览器" : "Saved only in this browser"}</p>
              <p className="mt-4">J / K {zh ? "选择本页警报" : "select on this page"}</p>
            </div>
          </aside>

          <section className="alerts-inbox min-w-0 border-r border-tm-rule" aria-label={zh ? "警报列表" : "Alert list"}>
            <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-tm-rule bg-tm-bg-2 px-4 py-2 text-xs">
              <span className="font-semibold text-tm-fg">{queueLabel(queue, zh)} · {data ? visible.length : "—"}</span>
              <TmInput aria-label={zh ? "搜索警报" : "Search alerts"} placeholder={zh ? "搜索标的或变化" : "Search ticker or change"} value={search} onChange={value=>{setSearch(value);setPage(1);}} className="w-56 max-w-full" />
            </div>
            <div className="flex min-h-7 shrink-0 items-center justify-between gap-3 border-b border-tm-rule px-4 text-xs text-tm-muted"><span>{zh ? "按决策优先级排序" : "Ranked by decision priority"}</span><span>{zh ? "选择一条，右侧查看与处理" : "Select to inspect and act"}</span></div>
            <div ref={listScrollRef} className="alerts-list-scroll">
            {error && data ? (
              <div role="alert" className="flex items-center justify-between gap-3 border-b border-tm-neg/50 bg-tm-neg/5 px-4 py-2 text-xs">
                <span className="text-tm-neg">{zh ? "刷新失败，显示上次可用队列。" : "Refresh failed; showing the last available queue."}</span>
                <TmButton type="button" onClick={() => void load()} variant="danger" size="xs">
                  {zh ? "重试" : "Retry"}
                </TmButton>
              </div>
            ) : null}
            {authRequired ? (
              <div className="flex min-h-[360px] items-center justify-center border-b border-tm-rule bg-tm-bg-2/30 p-6 text-center">
                <div className="max-w-md">
                  <ShieldAlert className="mx-auto h-7 w-7 text-tm-muted" />
                  <h2 className="mt-3 text-sm">{zh ? "登录后启用决策分诊" : "Sign in for decision triage"}</h2>
                  <p className="mt-2 text-xs leading-5 text-tm-muted">
                    {zh ? "持仓、今日候选、关注列表与处理状态都属于你的账户上下文。" : "Positions, picks, watchlists, and triage state belong to your account context."}
                  </p>
                  <TmLinkButton href="/login" variant="primary" size="sm" className="mt-4">
                    {zh ? "前往登录" : "Sign in"}
                  </TmLinkButton>
                </div>
              </div>
            ) : !data ? (
              <TmStatePane
                state={error ? "error" : "loading"}
                title={error
                  ? (zh ? "警报队列加载失败" : "Alert queue failed to load")
                  : (zh ? "正在建立决策上下文" : "Building decision context")}
                description={error ?? (zh
                  ? "正在读取数据源、持仓与候选关联。"
                  : "Loading feed, position, and recommendation relationships.")}
                action={error ? {
                  label: zh ? "重试此队列" : "Retry this queue",
                  onClick: () => void load(),
                  variant: "secondary",
                } : undefined}
                className="min-h-[360px] rounded-none border-0 border-b border-tm-rule"
              />
            ) : visible.length === 0 ? (
              <TmStatePane
                state="empty"
                title={hasFilters ? (zh ? "没有符合筛选条件的警报" : "No alerts match your filters") : queue === "needs_action"
                  ? (zh ? "当前没有需要立即处理的警报" : "Nothing needs immediate action")
                  : (zh ? "这个队列目前为空" : "This queue is empty")}
                description={zh
                  ? "更改筛选条件或刷新队列以检查新变化。"
                  : "Change the filters or refresh the queue to check for new changes."}
                action={{
                  label: hasFilters ? (zh ? "清除筛选" : "Clear filters") : (zh ? "刷新队列" : "Refresh queue"),
                  onClick: hasFilters ? clearFilters : () => void load(),
                  variant: "secondary",
                }}
                className="h-full min-h-80 rounded-none border-0"
              />
            ) : (
              <div key={`${queue}-${currentPage}`} className="alerts-page-enter divide-y divide-tm-rule">
                {pageItems.map((item) => {
                  const active = selected?.id === item.id;
                  return (
                    <TmRowButton
                      key={item.id}
                      data-alert-row
                      aria-pressed={active}
                      aria-controls="alert-inspector"
                      onClick={() => setSelectedId(item.id)}
                      className={`alerts-inbox-row w-full border-l-2 px-4 py-3 text-left transition-colors ${active ? "border-tm-accent bg-tm-accent-soft" : "border-transparent hover:bg-tm-bg-2"}`}
                    >
                      <div className="flex flex-wrap items-center gap-2"><span className="min-w-16 font-semibold text-lg">{item.ticker}</span><span className={`border px-1.5 py-0.5 text-xs ${SEVERITY_CLASS[item.severity]}`}>{severityLabel(item.severity, locale)}</span><span className="text-xs text-tm-muted">{alertTypeLabel(item, locale)}</span>{(item.occurrences ?? 1) > 1 ? <span className="border border-tm-rule px-1.5 py-0.5 text-xs text-tm-fg-2" title={zh ? `同一标的同类警报在美东同一天出现 ${item.occurrences} 次，已合并显示` : `${item.occurrences} same-type alerts for this ticker on one New York date, shown as one`}>{zh ? `同日 ${item.occurrences} 次` : `${item.occurrences}× today`}</span> : null}<time dateTime={item.created_at} className="ml-auto shrink-0 text-xs tabular-nums text-tm-muted">{stamp(item.created_at)} · {relativeTime(item.created_at, locale)}</time></div>
                      <p className="mt-1.5 text-sm leading-5 text-tm-fg">{changeSummary(item, locale)}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-tm-muted"><span>{relevanceLabel(item.relevance, locale)}{item.context.recommendation_rank ? ` #${item.context.recommendation_rank}` : ""}</span><span className={item.confidence === "low" ? "text-tm-warn" : ""}>{zh ? "证据" : "Evidence"} {confidenceLabel(item.confidence,locale)} · {item.confidence_score}/100</span><span>{item.source_count} {zh ? "个来源" : "source(s)"}</span><span className="ml-auto">{workflowLabel(item.state.status,locale)}{active ? " · ✓" : ""}</span></div>
                    </TmRowButton>
                  );
                })}
              </div>
            )}
            </div>
            <TmPagination page={currentPage} pageSize={pageSize} totalItems={visible.length} pageSizeOptions={[5]} onPageChange={setPage} onPageSizeChange={()=>{}} disabled={!data || authRequired} labels={{navigation:zh ? "警报分页" : "Alert pagination",previous:zh ? "上一页" : "Previous",previousAriaLabel:zh ? "上一页警报" : "Previous alerts",next:zh ? "下一页" : "Next",nextAriaLabel:zh ? "下一页警报" : "Next alerts",page:(current,total)=>`${current} / ${total}`,pageSize:zh ? "每页" : "Per page",total:total=>zh ? `共 ${total} 条 · 每页 5 条` : `${total} alerts · 5 per page`}} className="shrink-0" />
          </section>

          <aside ref={inspectorRef} id="alert-inspector" className="alerts-inspector min-w-0 bg-tm-bg-2" aria-label={zh ? "警报详情" : "Alert details"}>
            {!selected ? (
              <div className="flex h-full items-center justify-center p-6 text-center text-xs text-tm-muted">
                {zh ? "选择一条警报查看证据和关联对象。" : "Select an alert to inspect its evidence and linked objects."}
              </div>
            ) : (
              <div>
                <div className="flex min-h-12 items-center justify-between border-b border-tm-rule px-4 text-xs">
                  <h2 className="font-tm-mono text-[18px] font-semibold">{selected.ticker}</h2>
                  <span className={SEVERITY_CLASS[selected.severity].split(" ")[1]}>
                    {severityLabel(selected.severity, locale)} · {workflowLabel(selected.state.status,locale)}
                  </span>
                </div>
                <section className="border-b border-tm-rule px-4 py-3">
                  <p className="text-sm leading-6 text-tm-fg">{changeSummary(selected,locale)}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <TmButton disabled={busyId !== null} loading={busyId === selected.id} onClick={()=>void persistState(selected,selected.state.status === "resolved" ? "open" : "resolved")} className="col-span-2">
                      <CheckCircle2 className="h-3.5 w-3.5" />{selected.state.status === "resolved" ? (zh ? "重新打开" : "Reopen alert") : (selected.occurrences ?? 1) > 1 ? (zh ? `一并处理本组 ${selected.occurrences} 条` : `Resolve all ${selected.occurrences} in group`) : (zh ? "标记已处理" : "Mark resolved")}
                    </TmButton>
                    <TmButton disabled={busyId !== null} onClick={()=>void persistState(selected,"snoozed",new Date(Date.now()+4*3600_000).toISOString())} variant="secondary" size="sm"><Clock3 className="h-3 w-3" />{zh ? "稍后 4 小时" : "Snooze 4h"}</TmButton>
                    <TmLinkButton href={`/stock/${selected.ticker}#news`} variant="secondary" size="sm"><ExternalLink className="h-3 w-3" />{zh ? "打开研究" : "Research"}</TmLinkButton>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-tm-muted">{(selected.occurrences ?? 1) > 1 ? (zh ? `本组为同一标的、同类、美东同一天的 ${selected.occurrences} 条重复警报（首次 ${stamp(selected.first_seen_at ?? selected.created_at)}）；处理与稍后提醒作用于整组，可撤销。` : `${selected.occurrences} repeats of this ticker and type on one New York date (first ${stamp(selected.first_seen_at ?? selected.created_at)}); actions apply to the whole group and can be undone.`) : null}{zh ? "处理后可撤销，不会触发交易。" : "Actions support undo and never place trades."}</p>
                </section>

                <section className="border-b border-r border-tm-rule p-4 min-[1680px]:border-r-0">
                  <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "变化证据" : "Change evidence"}
                  </h2>
                  {selected.stale ? <p className="mt-2 text-xs leading-5 text-tm-warn">{zh ? "历史事件：请先确认最新情况，再判断影响。" : "Historical event: check current conditions before acting."}</p> : null}
                  <div className="mt-4 border border-tm-rule bg-tm-bg px-3 py-3">
                    <p className="text-xs uppercase tracking-[0.1em] text-tm-muted">{zh ? "证据时间窗" : "Evidence window"}</p>
                    <div className="relative mt-3 flex items-start justify-between before:absolute before:left-2 before:right-2 before:top-1.5 before:h-px before:bg-tm-rule">
                      {[
                        [zh ? "事件产生" : "Event", selected.created_at],
                        [selected.state.updated_at ? (zh ? "最近处理" : "Last action") : (zh ? "尚未处理" : "Not reviewed"), selected.state.updated_at],
                        [zh ? "队列读取" : "Fetched", data?.as_of],
                      ].map(([label, stamp], index) => (
                        <div key={`${label}-${index}`} className="relative z-10 w-1/3 text-center">
                          <span className={`mx-auto block h-3 w-3 rounded-full border ${index === 0 ? "border-tm-warn bg-tm-warn" : index === 2 ? "border-tm-accent bg-tm-accent" : "border-tm-rule bg-tm-bg"}`} />
                          <p className="mt-2 text-xs text-tm-fg-2">{label}</p>
                          <p className="mt-0.5 text-xs leading-5 tabular-nums text-tm-muted">{stamp ? new Date(stamp).toLocaleString(zh ? "zh-CN" : "en-US", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : "—"}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mt-3 divide-y divide-tm-rule border border-tm-rule">
                    {evidenceRows(selected,locale).length > 0 ? evidenceRows(selected,locale).map(([key, value]) => (
                      <div key={key} className="flex min-h-8 items-center justify-between px-3 py-1.5 text-xs">
                        <span className="text-tm-muted">{key}</span>
                        <span className="max-w-[190px] break-words text-right font-mono text-tm-fg-2">{value}</span>
                      </div>
                    )) : (
                      <p className="px-2 py-2 text-xs text-tm-muted">
                        {zh ? "当前事件没有更多结构化字段。" : "No additional structured facts are available."}
                      </p>
                    )}
                  </div>
                  <p className="mt-2 text-xs leading-4 text-tm-muted">
                    {zh ? "事件与指标同期发生，仅作相关性线索，不推断因果。" : "Events and metrics are contemporaneous evidence only; no causal claim is inferred."}
                  </p>
                </section>

                <section className="border-b border-r border-tm-rule p-4 min-[1680px]:border-r-0">
                  <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-tm-accent">
                    {zh ? "决策影响" : "Decision impact"}
                  </h2>
                  <p className="mt-2 text-xs leading-5 text-tm-fg-2">{impactSummary(selected, locale)}</p>
                  <div className="mt-3 grid grid-cols-2 gap-px bg-tm-rule border border-tm-rule text-xs">
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
                      <p className={`mt-1 ${selected.confidence === "low" ? "text-tm-warn" : "text-tm-fg"}`}>{confidenceLabel(selected.confidence,locale)} · {selected.confidence_score}/100</p>
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
                  <div className="mt-2 flex gap-2 text-xs">
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

                <section className="p-4 text-xs leading-5 text-tm-muted">
                    <p>{zh ? "当前状态" : "Current state"}: <span className="text-tm-fg-2">{workflowLabel(selected.state.status,locale)}</span></p>
                    <p>{zh ? "最近更新" : "Last update"}: {selected.state.updated_at ? new Date(selected.state.updated_at).toLocaleString(zh ? "zh-CN" : "en-US") : (zh ? "尚无处理记录" : "No triage action yet")}</p>
                </section>
              </div>
            )}
          </aside>
        </div>
        <section className="alerts-audit border-x border-b border-tm-rule">
          <TmDisclosureButton expanded={auditExpanded} onClick={()=>setAuditExpanded(value=>!value)} label={zh ? "处理记录" : "Review history"} meta={zh ? `${auditCandidates.length} 条 · 本次载入记录的最近状态` : `${auditCandidates.length} · latest state of loaded records`} aria-controls="alert-review-history" />
          {auditExpanded ? <div id="alert-review-history" className="max-h-48 overflow-auto">
          <div className="grid h-9 grid-cols-[190px_100px_120px_minmax(0,1fr)_120px] items-center gap-3 border-b border-tm-rule bg-tm-bg-2/40 px-4 text-xs uppercase tracking-[0.08em] text-tm-muted">
            <span>{zh ? "处理时间" : "Action time"}</span>
            <span>{zh ? "标的" : "Ticker"}</span>
            <span>{zh ? "动作" : "Action"}</span>
            <span>{zh ? "状态说明" : "Status note"}</span>
            <span>{zh ? "可恢复" : "Recovery"}</span>
          </div>
          {auditItems.length > 0 ? auditItems.map((item) => (
            <div key={`audit-${item.id}`} className="grid min-h-9 grid-cols-[190px_100px_120px_minmax(0,1fr)_120px] items-center gap-3 border-b border-tm-rule px-4 text-xs last:border-b-0">
              <span className="text-tm-muted">{item.state.updated_at ? new Date(item.state.updated_at).toLocaleString(zh ? "zh-CN" : "en-US") : "—"}</span>
              <span className="font-mono text-tm-fg">{item.ticker}</span>
              <span className="text-tm-fg-2">{workflowLabel(item.state.status,locale)}</span>
              <span className="truncate text-tm-muted">{item.state.note ?? (zh ? "状态由当前账户更新" : "State updated by the current account")}</span>
              <TmButton variant="ghost" size="xs" onClick={()=>{setQueue(queueFor(item));clearFilters();setPage(Math.floor((data?.alerts.filter(row=>queueFor(row)===queueFor(item)).findIndex(row=>row.id===item.id) ?? 0)/pageSize)+1);setSelectedId(item.id);}}>{zh ? "查看记录" : "View record"}</TmButton>
            </div>
          )) : (
            <div className="flex min-h-12 items-center px-4 text-xs text-tm-muted">
              {zh ? "当前没有处理记录。完成一次稍后提醒或标记处理后，记录会显示在这里。" : "No triage actions yet. Snooze or resolve an item to create an audit entry."}
            </div>
          )}
          </div> : null}
        </section>
        </div>

      <footer className="flex min-h-7 shrink-0 flex-wrap items-center justify-between gap-x-3 border-t border-tm-rule px-4 py-1 text-xs text-tm-muted">
        <span>{zh ? "数据仅供研究参考，不构成投资建议，也不代表系统可执行任何交易。" : "Research only. Not investment advice and not an automated trading instruction."}</span>
        <span>{zh ? "排序可解释，可撤销，有审计记录" : "Explainable ranking · reversible · auditable"}</span>
      </footer>
    </TmScreen>
  );
}
