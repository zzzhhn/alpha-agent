"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { TmPane, TmScreen } from "@/components/tm/TmPane";
import { TmButton, TmDisclosureButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmTable, TmTableBody, TmTableCell, TmTableFrame, TmTableHead, TmTableHeaderCell, TmTableRow } from "@/components/tm/TmTable";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { t } from "@/lib/i18n";
import type { AccountResponse, EquityCurveResponse, OrderListResponse, OrderOut } from "@/lib/api/paper";
import {
  fetchPaperAccounts, fetchBotAccount, fetchBotCurve, fetchBotOrders, fetchPaperBotConfig,
  fetchPaperBotRuns, fetchPaperBotRun, startPaperBotRun, stopPaperBotRun, patchPaperBotConfig, fetchPaperBotPerformance,
  isActivePaperRun, canWakePaperBot, type PaperAccountSummary, type PaperBotConfig, type PaperBotRun, type PaperBotRunList, type PaperBotPerformance,
} from "@/lib/api/paper-bot";
import { Metric } from "./PaperUi";
import PaperBotConfigDrawer from "./PaperBotConfigDrawer";
import { PaperBotState, PaperBotPagination, PaperBotRunDrawer, PaperBotOrderDrawer, PaperBotActions, PaperBotOutcome, botTime, botRunLabel, botStageLabel, botTriggerLabel } from "./PaperBotUi";
import { PaperBotReadiness, PaperBotPerformanceSummary, PaperBotPerformanceDrawer, PaperBotScheduleDrawer } from "./PaperBotEvidence";
import PaperPositionsWithSource from "./PaperPositionsWithSource";
import PaperCurvePane from "./PaperCurvePane";
import PaperOrdersPane from "./PaperOrdersPane";
import RecommendationPerformance from "../RecommendationPerformance";

export default function PaperBotScreen({ accountTabs }: { readonly accountTabs: ReactNode }) {
  const { locale } = useLocale();
  const [account,setAccount] = useState<PaperAccountSummary | null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState<unknown>(null);
  const [creating,setCreating] = useState(false);
  const request = useRef({version:0});
  const load = useCallback(async () => {
    const version = ++request.current.version; setLoading(true); setError(null);
    try { const result = await fetchPaperAccounts(); if (version === request.current.version) setAccount(result.accounts.find(row=>row.kind === "bot") ?? null); }
    catch (reason) { if (version === request.current.version) setError(reason); }
    finally { if (version === request.current.version) setLoading(false); }
  },[]);
  useEffect(()=>{const state=request.current;void load();return ()=>{state.version++;};},[load]);
  if (account && !error) return <BotWorkspace key={account.account_id} summary={account} accountTabs={accountTabs} />;
  // The account name is unknown during discovery; don't flash a different title.
  const title = account?.name || (loading ? <>
    <span aria-hidden="true" className="inline-block h-[1em] w-[5em] align-middle bg-tm-bg-3" />
    <span className="sr-only">{t(locale,"common.loading")}</span>
  </> : t(locale,"sim.bot.title"));
  return <TmScreen className="overflow-y-auto"><WorkbenchHeader title={title} subtitle={t(locale,"sim.bot.subtitle")} action={<TmButton variant="secondary" loading={loading} onClick={()=>void load()}>{t(locale,"sim.bot.refresh")}</TmButton>} />{accountTabs}
    {loading || error ? <PaperBotState loading={loading} error={error} onRetry={()=>void load()} /> : <TmStatePane state="empty" title={t(locale,"sim.bot.empty")} description={t(locale,"sim.bot.empty_hint")} action={{label:t(locale,"sim.bot.create"),onClick:()=>setCreating(true),variant:"primary"}} className="m-4" />}
    {creating ? <PaperBotConfigDrawer open onClose={()=>{setCreating(false);void load();}} account={null} config={null} onSaved={setAccount} /> : null}
  </TmScreen>;
}

type Resource<T> = { readonly data: T | null; readonly error: unknown; readonly loading: boolean };
const pending = <T,>(): Resource<T> => ({data:null,error:null,loading:true});
const money = (value: number) => `$${value.toLocaleString("en-US",{maximumFractionDigits:0})}`;

function BotWorkspace({ summary, accountTabs }: { readonly summary: PaperAccountSummary; readonly accountTabs: ReactNode }) {
  const { locale } = useLocale();
  const id = summary.account_id;
  const [account,setAccount] = useState<Resource<AccountResponse>>(pending);
  const [config,setConfig] = useState<Resource<PaperBotConfig>>(pending);
  const [curve,setCurve] = useState<Resource<EquityCurveResponse>>(pending);
  const [performance,setPerformance] = useState<Resource<PaperBotPerformance>>(pending);
  const [performanceOpen,setPerformanceOpen] = useState(false);
  const [scheduleOpen,setScheduleOpen] = useState(false);
  const [latest,setLatest] = useState<Resource<PaperBotRun>>(pending);
  const [runs,setRuns] = useState<Resource<PaperBotRunList>>(pending);
  const [orders,setOrders] = useState<Resource<OrderListResponse>>(pending);
  const [runPage,setRunPage] = useState(1);
  const [orderPage,setOrderPage] = useState(1);
  const [ledger,setLedger] = useState<"runs" | "orders">("runs");
  const [revision,setRevision] = useState(0);
  const [configDraft,setConfigDraft] = useState<PaperBotConfig | null>(null);
  const [details,setDetails] = useState<PaperBotRun | null>(null);
  const [detailsLoading,setDetailsLoading] = useState(false);
  const [detailsError,setDetailsError] = useState<unknown>(null);
  const [orderDetails,setOrderDetails] = useState<OrderOut | null>(null);
  const [researchOpen,setResearchOpen] = useState(false);
  const [busy,setBusy] = useState(false);
  const [actionError,setActionError] = useState<unknown>(null);
  const [pollError,setPollError] = useState(false);
  const alive = useRef(true);
  const busyRef = useRef(false);
  const mutationVersion = useRef(0);
  const detailRequestVersion = useRef(0);
  const refresh = useCallback(()=>setRevision(value=>value+1),[]);
  useEffect(()=>{alive.current=true; return ()=>{alive.current=false;};},[]);

  useEffect(()=>{
    let cancelled=false;
    const version=mutationVersion.current;
    const read = async <T,>(fetcher:()=>Promise<T>, setter:(value:Resource<T>)=>void) => {
      setter({data:null,error:null,loading:true});
      try {const data=await fetcher(); if(!cancelled && version===mutationVersion.current) setter({data,error:null,loading:false});}
      catch(error){if(!cancelled && version===mutationVersion.current) setter({data:null,error,loading:false});}
    };
    void read(()=>fetchBotAccount(id),setAccount);
    void read(()=>fetchPaperBotConfig(id),setConfig);
    void read(()=>fetchBotCurve(id),setCurve);
    void read(()=>fetchPaperBotPerformance(id),setPerformance);
    setLatest(previous=>({...previous,error:null,loading:true}));
    void fetchPaperBotRuns(id,1,0).then(result=>{if(!cancelled && version===mutationVersion.current) setLatest({data:result.runs[0] ?? null,error:null,loading:false});}).catch(error=>{if(!cancelled && version===mutationVersion.current)setLatest({data:null,error,loading:false});});
    return ()=>{cancelled=true;};
  },[id,revision]);

  useEffect(()=>{
    let cancelled=false; const version=mutationVersion.current; setRuns(pending());
    void fetchPaperBotRuns(id,5,(runPage-1)*5).then(data=>{if(!cancelled && version===mutationVersion.current)setRuns({data,error:null,loading:false});}).catch(error=>{if(!cancelled && version===mutationVersion.current)setRuns({data:null,error,loading:false});});
    return ()=>{cancelled=true;};
  },[id,runPage,revision]);
  useEffect(()=>{
    let cancelled=false; const version=mutationVersion.current; setOrders(pending());
    void fetchBotOrders(id,5,(orderPage-1)*5).then(data=>{if(!cancelled && version===mutationVersion.current)setOrders({data,error:null,loading:false});}).catch(error=>{if(!cancelled && version===mutationVersion.current)setOrders({data:null,error,loading:false});});
    return ()=>{cancelled=true;};
  },[id,orderPage,revision]);

  const current = latest.data;
  const active = isActivePaperRun(current);
  const activeId = active ? current?.id : null;
  useEffect(()=>{
    if(!activeId) return;
    let cancelled=false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight=false;
    async function poll() {
      if(cancelled || document.hidden || inFlight) return;
      inFlight=true;
      const version=mutationVersion.current;
      try {
        const run=await fetchPaperBotRun(id,activeId!);
        if(cancelled) return;
        if(version === mutationVersion.current) {
          setLatest({data:run,error:null,loading:false}); setPollError(false);
          setDetails(previous=>previous?.id===run.id ? run : previous);
          if(!isActivePaperRun(run)){refresh();return;}
        }
      } catch {if(!cancelled && version===mutationVersion.current)setPollError(true);}
      finally {inFlight=false;}
      if(!cancelled && !document.hidden) timer=setTimeout(()=>void poll(),5000);
    }
    function visibility(){if(timer)clearTimeout(timer); if(!document.hidden)void poll();}
    document.addEventListener("visibilitychange",visibility);
    if(!document.hidden) timer=setTimeout(()=>void poll(),3000);
    return ()=>{cancelled=true;if(timer)clearTimeout(timer);document.removeEventListener("visibilitychange",visibility);};
  },[id,activeId,refresh]);

  async function mutate(action:()=>Promise<unknown>) {
    if(busyRef.current) return;
    busyRef.current=true;setBusy(true);setActionError(null);
    mutationVersion.current++;
    try {await action();}
    catch(error){if(alive.current)setActionError(error);}
    finally {busyRef.current=false;if(alive.current){setBusy(false);refresh();}}
  }
  async function inspectRun(run: PaperBotRun) {
    const version=++detailRequestVersion.current;
    setDetails(run);setDetailsLoading(true);setDetailsError(null);
    try {const fresh=await fetchPaperBotRun(id,run.id);if(alive.current && version===detailRequestVersion.current)setDetails(fresh);}
    catch(error){if(alive.current && version===detailRequestVersion.current)setDetailsError(error);}
    finally {if(alive.current && version===detailRequestVersion.current)setDetailsLoading(false);}
  }
  const cfg=config.data;
  const acc=account.data;
  const marksMissing=acc ? acc.portfolio_value === null || acc.unrealized_pnl === null || acc.total_return_pct === null || acc.positions.some(position=>position.current_price === null) : false;
  const runNow = () => mutate(async()=>{const run=await startPaperBotRun(id);if(alive.current)setLatest({data:run,error:null,loading:false});});
  const returnPct=acc?.total_return_pct;
  return <TmScreen className="overflow-y-auto paper-bot-appear">
    <WorkbenchHeader title={summary.name || t(locale,"sim.bot.title")} subtitle={t(locale,"sim.bot.subtitle")} statuses={[
      {label:t(locale,"sim.bot.model"),value:cfg ? `${cfg.provider} / ${cfg.model}` : "—"},
      {label:t(locale,"sim.bot.readiness"),value:cfg?.readiness ? t(locale,cfg.readiness.can_wake ? "sim.bot.can_wake" : "sim.bot.cannot_wake") : "—",tone:cfg?.readiness && !cfg.readiness.can_wake ? "warning" : "default"},
      {label:t(locale,"sim.bot.next"),value:cfg?.schedule_enabled ? `${botTime(cfg.next_wake_at,locale)} CST` : cfg ? t(locale,"sim.bot.paused") : "—"},
    ]} action={<div className="flex flex-wrap gap-2">
      <TmButton variant="secondary" onClick={refresh} disabled={busy}>{t(locale,"sim.bot.refresh")}</TmButton>
      <TmButton variant="secondary" onClick={()=>setConfigDraft(cfg)} disabled={!cfg || busy}>{t(locale,"sim.bot.configure")}</TmButton>
      <TmButton onClick={()=>void runNow()} loading={busy} disabled={active || latest.loading || !!latest.error || !canWakePaperBot(cfg)}>{active ? t(locale,"sim.bot.status.running") : t(locale,"sim.bot.wake")}</TmButton>
    </div>} />
    {accountTabs}
    {actionError ? <PaperBotState error={actionError} onRetry={()=>{setActionError(null);refresh();}} /> : null}
    <TmPane title={t(locale,"sim.account.tab")} meta={cfg ? `${t(locale,"sim.bot.version")} ${cfg.config_version}` : "—"}>
      <div className="grid grid-cols-2 gap-4 px-6 py-4 sm:grid-cols-4">
        <Metric label={t(locale,"sim.account.nav")} value={acc?.portfolio_value != null && !marksMissing ? money(acc.portfolio_value) : "—"} />
        <Metric label={t(locale,"sim.account.cash")} value={acc ? money(acc.available_cash) : "—"} />
        <Metric label={t(locale,"sim.account.unrealized")} value={acc?.unrealized_pnl != null && !marksMissing ? `${acc.unrealized_pnl > 0 ? "+" : acc.unrealized_pnl < 0 ? "-" : ""}${money(Math.abs(acc.unrealized_pnl))}` : "—"} tone={!marksMissing && acc?.unrealized_pnl ? acc.unrealized_pnl>0 ? "text-tm-pos" : "text-tm-neg" : "text-tm-fg"} />
        <Metric label={t(locale,"sim.workspace.total_return")} value={returnPct == null || marksMissing ? "—" : `${returnPct>0 ? "+" : ""}${returnPct.toFixed(2)}%`} tone={!marksMissing && returnPct ? returnPct>0 ? "text-tm-pos" : "text-tm-neg" : "text-tm-fg"} />
      </div>
      {marksMissing ? <p role="status" className="px-6 pb-3 text-xs leading-5 text-tm-warn">{t(locale,"sim.bot.missing_marks")}</p> : null}
      {acc?.valued_at ? <p className="px-6 pb-3 text-xs text-tm-muted">{t(locale,"sim.bot.valued_at")} · {botTime(acc.valued_at,locale)} CST</p> : null}
      {account.error ? <PaperBotState error={account.error} onRetry={refresh} /> : null}
    </TmPane>
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
      <div className="min-w-0 lg:border-r lg:border-tm-rule">
        <TmPane title={t(locale,active ? "sim.bot.decision" : "sim.bot.last_decision")} meta={current ? `${botTime(current.created_at,locale)} CST` : "—"}>
          {(latest.loading && !current) || latest.error ? (
            <PaperBotState loading={latest.loading} error={latest.error} onRetry={refresh} />
          ) : current ? <div className="space-y-3 px-6 py-5">
            <div role="status" aria-live="polite" className="font-tm-mono text-xs text-tm-accent">{botStageLabel(locale,current)}</div>
            <p className="line-clamp-3 whitespace-pre-wrap break-words text-sm leading-6 text-tm-fg">{current.summary || (active ? t(locale,"sim.bot.running_hint") : current.status === "no_trade" ? t(locale,"sim.bot.no_trade") : current.status === "failed" ? t(locale,"sim.bot.run_error") : t(locale,"sim.bot.no_result"))}</p>
            <PaperBotOutcome run={current} />
            <div className="[&_li_p]:line-clamp-2"><PaperBotActions run={current} limit={4} /></div>
            <p className="text-xs leading-5 text-tm-muted">{t(locale,active ? "sim.bot.running_hint" : "sim.bot.completed_hint")}</p>
            <TmButton variant="secondary" onClick={()=>void inspectRun(current)}>{t(locale,"sim.bot.details")}</TmButton>
            {pollError ? <p role="alert" className="text-xs text-tm-neg">{t(locale,"sim.bot.stale_poll")}</p> : null}
          </div> : <TmStatePane state="empty" title={t(locale,"sim.bot.no_runs")} description={t(locale,"sim.bot.no_runs_hint")} className="border-0 !bg-transparent" />}
        </TmPane>
        <TmPane title={t(locale,"sim.bot.curve")} meta={curve.data?.base_date ?? "—"}>{curve.loading || curve.error ? <PaperBotState loading={curve.loading} error={curve.error} onRetry={refresh} /> : <PaperCurvePane curve={curve.data} compact showDisclaimer={false} />}</TmPane>
      </div>
      <div className="min-w-0"><TmPane title={t(locale,"sim.bot.run_panel")}>
        {config.loading || config.error ? <PaperBotState loading={config.loading} error={config.error} onRetry={refresh} /> : cfg ? <div className="space-y-4 px-4 py-4 text-xs leading-5 text-tm-muted">
          <PaperBotReadiness config={cfg} />
          <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold text-tm-fg">{t(locale,cfg.schedule_enabled ? "sim.bot.scheduled" : "sim.bot.paused")}</span><TmButton variant="secondary" disabled={busy || (!cfg.schedule_enabled && !cfg.credential_configured)} onClick={()=>void mutate(()=>patchPaperBotConfig(id,{schedule_enabled:!cfg.schedule_enabled}))}>{t(locale,cfg.schedule_enabled ? "sim.bot.pause" : "sim.bot.resume")}</TmButton></div>
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-2"><dt>{t(locale,"sim.bot.open_slot")}</dt><dd>{cfg.open_enabled ? `${cfg.open_offset_minutes} ${t(locale,"sim.bot.minutes")}` : "—"}</dd><dt>{t(locale,"sim.bot.close_slot")}</dt><dd>{cfg.close_enabled ? `${cfg.close_offset_minutes} ${t(locale,"sim.bot.minutes")}` : "—"}</dd><dt>{t(locale,"sim.bot.daily_runs")}</dt><dd>{cfg.max_daily_runs}</dd><dt>{t(locale,"sim.bot.market_day")}</dt><dd>{cfg.market.session_date}</dd></dl>
          <div className="border-t border-tm-rule pt-3"><p className="text-tm-fg">{t(locale,"sim.bot.next")} · {botTime(cfg.next_wake_at,locale,"America/New_York")} ET</p><p>{botTime(cfg.next_wake_at,locale)} CST</p></div>
          <p>{t(locale,cfg.market.is_open ? "sim.bot.market_open" : "sim.bot.market_closed_hint")}</p>
          <TmButton variant="secondary" size="xs" onClick={()=>setScheduleOpen(true)}>{t(locale,"sim.bot.schedule_observations")}</TmButton>
          {!cfg.credential_configured ? <p className="text-tm-warn">{t(locale,"sim.bot.byok_missing")} <TmLinkButton href="/settings">{t(locale,"sim.bot.settings")}</TmLinkButton></p> : null}
          {active && current ? <div className="border-t border-tm-rule pt-3"><TmButton variant="secondary" disabled={busy} onClick={()=>void mutate(async()=>{const run=await stopPaperBotRun(id,current.id);if(alive.current)setLatest({data:run,error:null,loading:false});})}>{t(locale,"sim.bot.stop")}</TmButton><p className="mt-2">{t(locale,"sim.bot.stop_hint")}</p></div> : null}
        </div> : null}
      </TmPane></div>
    </div>
    <TmPane title={t(locale,"sim.bot.positions")} meta={acc ? `${acc.positions.length}` : "—"}>{account.loading || account.error ? <PaperBotState loading={account.loading} error={account.error} onRetry={refresh} /> : acc ? <PaperPositionsWithSource accountKind="bot" positions={acc.positions} attribution={[]} attributionAvailable={false} pendingOrders={acc.pending_orders} /> : null}</TmPane>
    <TmPane title={t(locale,"sim.bot.performance.title")} meta={t(locale,"sim.bot.performance.current_cohort")}>
      {performance.loading || performance.error ? <PaperBotState loading={performance.loading} error={performance.error} onRetry={refresh} /> : performance.data ? <PaperBotPerformanceSummary data={performance.data} onDetails={()=>setPerformanceOpen(true)} /> : null}
    </TmPane>
    <TmPane title={t(locale,ledger === "runs" ? "sim.bot.history" : "sim.bot.orders")} meta={t(locale,"sim.bot.records_timezone")}>
      <SegmentedTabs<"runs" | "orders"> active={ledger} onChange={setLedger} ariaLabel={t(locale,"sim.bot.history")} items={[{key:"runs",label:t(locale,"sim.bot.history")},{key:"orders",label:t(locale,"sim.bot.orders")}]} />
      <div key={`${ledger}-${ledger === "runs" ? runPage : orderPage}`} className="paper-bot-appear">
      {ledger === "runs" ? (
        runs.loading || runs.error ? <PaperBotState loading={runs.loading} error={runs.error} onRetry={refresh} /> : <>
          <TmTableFrame><TmTable density="compact" caption={t(locale,"sim.bot.history")}>
            <TmTableHead><TmTableRow>
              {(["sim.bot.time","sim.bot.status","sim.bot.trigger","sim.bot.summary"] as const).map(key=><TmTableHeaderCell key={key}>{t(locale,key)}</TmTableHeaderCell>)}
              <TmTableHeaderCell>{t(locale,"sim.bot.details")}</TmTableHeaderCell>
            </TmTableRow></TmTableHead>
            <TmTableBody>{runs.data?.runs.map(run=><TmTableRow key={run.id}>
              <TmTableCell className="whitespace-nowrap">{botTime(run.created_at,locale)}</TmTableCell>
              <TmTableCell className="whitespace-nowrap">{botRunLabel(locale,run.status)}</TmTableCell>
              <TmTableCell>{botTriggerLabel(locale,run.trigger)}</TmTableCell>
              <TmTableCell className="max-w-sm truncate">{run.summary || "—"}</TmTableCell>
              <TmTableCell><TmButton variant="ghost" size="xs" aria-label={`${t(locale,"sim.bot.details")} ${botTime(run.created_at,locale)}`} onClick={()=>void inspectRun(run)}>{t(locale,"sim.bot.details")}</TmButton></TmTableCell>
            </TmTableRow>)}</TmTableBody>
          </TmTable></TmTableFrame>
          {runs.data?.total === 0 ? <p className="px-4 py-6 text-sm text-tm-muted">{t(locale,"sim.bot.no_runs")}</p> : null}
          <PaperBotPagination page={runPage} total={runs.data?.total ?? 0} loading={runs.loading} onChange={setRunPage} />
        </>
      ) : orders.loading || orders.error ? <PaperBotState loading={orders.loading} error={orders.error} onRetry={refresh} /> : <>
        <PaperOrdersPane botMode orders={orders.data?.orders ?? []} attribution={[]} attributionStatus="unavailable" onCancel={async()=>{}} onInspectOrder={setOrderDetails} showAttribution={false} showDisclaimer={false} />
        <PaperBotPagination page={orderPage} total={orders.data?.total ?? 0} loading={orders.loading} onChange={setOrderPage} />
        <p className="px-4 py-3 text-xs leading-5 text-tm-muted">{t(locale,"sim.bot.execution_note")}</p>
      </>}
      </div>
    </TmPane>
    <TmDisclosureButton expanded={researchOpen} onClick={()=>setResearchOpen(value=>!value)} label={locale === "zh" ? "系统策略验证" : "System policy validation"} meta={locale === "zh" ? "独立研究账户，不计入机器人收益" : "Independent research books, excluded from bot returns"} aria-controls="paper-bot-system-evidence" />{researchOpen ? <div id="paper-bot-system-evidence"><RecommendationPerformance /></div> : null}
    {configDraft ? <PaperBotConfigDrawer open onClose={()=>setConfigDraft(null)} account={summary} config={configDraft} onSaved={()=>{mutationVersion.current++;refresh();}} /> : null}
    <PaperBotRunDrawer run={details} loading={detailsLoading} error={detailsError} onRetry={()=>{if(details)void inspectRun(details);}} onClose={()=>{detailRequestVersion.current++;setDetails(null);setDetailsLoading(false);setDetailsError(null);}} />
    <PaperBotPerformanceDrawer data={performance.data} open={performanceOpen} onClose={()=>setPerformanceOpen(false)} />
    {cfg ? <PaperBotScheduleDrawer config={cfg} open={scheduleOpen} onClose={()=>setScheduleOpen(false)} onRun={runId=>{setScheduleOpen(false);const version=++detailRequestVersion.current;void fetchPaperBotRun(id,runId).then(run=>{if(alive.current && version===detailRequestVersion.current)setDetails(run);}).catch(error=>{if(alive.current && version===detailRequestVersion.current)setActionError(error);});}} /> : null}
    <PaperBotOrderDrawer order={orderDetails} onClose={()=>setOrderDetails(null)} onRun={runId=>{
      setOrderDetails(null);
      const version=++detailRequestVersion.current;
      void fetchPaperBotRun(id,runId).then(run=>{if(alive.current && version===detailRequestVersion.current)setDetails(run);}).catch(error=>{if(alive.current && version===detailRequestVersion.current)setActionError(error);});
    }} />
  </TmScreen>;
}
