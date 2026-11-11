"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";
import { TmButton } from "@/components/tm/TmButton";
import { TmDrawer } from "@/components/tm/TmDrawer";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import type { PaperBotConfig, PaperBotPerformance } from "@/lib/api/paper-bot";
import { botZonedTime, botReason, botTriggerLabel } from "./PaperBotUi";
import { Metric } from "./PaperUi";

export function PaperBotReadiness({ config }: { readonly config: PaperBotConfig }) {
  const { locale } = useLocale();
  const { timeZone } = useTimezonePreference();
  const ready=config.readiness;
  return <section aria-label={t(locale,"sim.bot.readiness")} className="space-y-2 border-b border-tm-rule pb-3">
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold text-tm-fg">{t(locale,"sim.bot.readiness")}</h3><span className={ready && !ready.can_wake ? "text-tm-warn" : "text-tm-fg"}>{t(locale,!ready ? "sim.bot.readiness_unknown" : ready.can_wake ? "sim.bot.can_wake" : "sim.bot.cannot_wake")}</span></div>
    {ready ? <>
      <ul className="space-y-1">{ready.blocked_reasons.map(reason=><li key={reason}>{botReason(locale,reason)}</li>)}</ul>
      {ready.warnings?.length ? <ul className="space-y-1 text-tm-warn">{ready.warnings.map(reason=><li key={reason}>{botReason(locale,reason)}</li>)}</ul> : null}
      <p className="font-tm-mono">{t(locale,"sim.bot.evaluated_at")} · {botZonedTime(ready.evaluated_at,locale,timeZone)}</p>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-1"><dt>{t(locale,"sim.bot.today_runs")}</dt><dd>{ready.today_runs} / {config.max_daily_runs}</dd><dt>{t(locale,"sim.bot.research_as_of")}</dt><dd>{botZonedTime(ready.research_as_of,locale,timeZone)}</dd><dt>{t(locale,"sim.bot.research_age")}</dt><dd>{ready.research_age_sessions ?? "—"}</dd></dl>
    </> : <p>{t(locale,"sim.bot.readiness_unknown_hint")}</p>}
    {!config.schedule_enabled ? <p>{t(locale,"sim.bot.manual_independent")}</p> : null}
  </section>;
}

const pct=(value:number | null, signed=false)=>value == null || !Number.isFinite(value) ? "—" : `${signed && value>0 ? "+" : ""}${value.toFixed(2)}%`;
const money=(value:number | null)=>value == null || !Number.isFinite(value) ? "—" : `$${value.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;

export function botSampleLength(data: {
  readonly matched_window: { readonly sample_count?: number | null };
  readonly history: { readonly valid_nav_count: number };
}, locale: Locale) {
  const count = data.matched_window.sample_count ?? data.history.valid_nav_count;
  return {
    count,
    label: t(locale, "sim.bot.performance.sample_length").replace("{n}", String(count)),
    tone: count < 252 ? "text-tm-warn" : "text-tm-muted",
  };
}

export function PaperBotPerformanceSummary({ data, onDetails }: { readonly data: PaperBotPerformance; readonly onDetails?: () => void }) {
  const { locale }=useLocale();
  const window=data.matched_window;
  const sample = botSampleLength(data, locale);
  return <div className="space-y-3 px-6 py-4">
    <p className="font-tm-mono text-xs leading-5 text-tm-muted"><span className="text-tm-fg">{t(locale,"sim.bot.close_performance")}</span> · {window.start_date && window.end_date ? `${window.start_date} → ${window.end_date} · ${t(locale,"sim.bot.performance.matched")}` : t(locale,window.reason === "exchange_calendar_unavailable" ? "sim.bot.performance.calendar_unavailable" : "sim.bot.performance.insufficient")}{window.start_date && !window.complete ? ` · ${t(locale,"sim.bot.performance.gaps")}` : ""}</p>
    <div className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-4"><Metric label={t(locale,"sim.bot.performance.bot_return")} value={pct(window.bot_return_pct,true)} /><Metric label="SPY" value={pct(window.spy_return_pct,true)} /><Metric label={t(locale,"sim.bot.performance.cash_return")} value={pct(window.cash_return_pct,true)} /><Metric label={t(locale,"sim.bot.performance.drawdown")} value={pct(window.complete ? window.bot_max_drawdown_pct : null)} /></div>
    <p className={`text-xs leading-5 ${sample.tone}`}>{sample.label}</p>
    <p className="text-xs leading-5 text-tm-muted">{t(locale,"sim.bot.performance.no_model_control")}</p>
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-tm-muted"><span>{t(locale,"sim.bot.performance.exposure")} {pct(data.valuation.exposure_pct)} · {t(locale,"sim.bot.performance.paid_fees")} {money(data.orders.paid_fees)} <span>({t(locale,"sim.bot.scope.account")})</span></span>{onDetails ? <TmButton variant="secondary" size="xs" onClick={onDetails}>{t(locale,"sim.bot.performance.details")}</TmButton> : null}</div>
  </div>;
}

export function PaperBotPerformanceDrawer({ data, open, onClose }: { readonly data: PaperBotPerformance | null; readonly open: boolean; readonly onClose: () => void }) {
  const { locale }=useLocale();
  const { timeZone } = useTimezonePreference();
  const turnoverReasons: Record<string,TranslationKey>={insufficient_common_observations:"sim.bot.performance.insufficient",incomplete_daily_path:"sim.bot.performance.gaps",undated_or_invalid_fills:"sim.bot.performance.invalid_fills",invalid_average_nav:"sim.bot.performance.invalid_average_nav",exchange_calendar_unavailable:"sim.bot.performance.calendar_unavailable"};
  return <TmDrawer open={open} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={t(locale,"sim.bot.performance.title")} width="lg">
    {data ? <div className="space-y-5 text-xs leading-5 text-tm-muted">
      <p>{t(locale,"sim.bot.performance.scope")}</p>
      <PaperBotPerformanceSummary data={data} />
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-3 font-tm-mono">
        <dt>{t(locale,"sim.bot.performance.history")} ({data.history.first_date ?? "—"} → {data.history.last_date ?? "—"})</dt><dd>{data.history.valid_nav_count} / {data.history.sample_count}</dd>
        <dt>{t(locale,"sim.bot.performance.matched_samples")}</dt><dd>{data.matched_window.sample_count} / {data.matched_window.expected_sessions ?? "—"}</dd>
        <dt>{t(locale,"sim.bot.performance.missing_sessions")}</dt><dd>{data.matched_window.missing_sessions ?? "—"}</dd>
        <dt>{t(locale,"sim.bot.performance.filled_pending")} · {t(locale,"sim.bot.scope.account")}</dt><dd>{data.orders.filled} / {data.orders.pending}</dd>
        <dt>{t(locale,"sim.bot.performance.failed_expired_cancelled")} · {t(locale,"sim.bot.scope.account")}</dt><dd>{data.orders.failed} / {data.orders.expired} / {data.orders.cancelled}</dd>
        <dt>{t(locale,"sim.bot.performance.turnover")}</dt><dd>{pct(data.turnover.ratio_pct)}</dd>
        <dt>{t(locale,"sim.bot.performance.token_scope")} ({data.llm.run_count})</dt><dd>{data.llm.prompt_tokens ?? "—"} / {data.llm.completion_tokens ?? "—"}</dd>
        <dt>{t(locale,"sim.bot.performance.model_cost")}</dt><dd>{money(data.llm.cost_usd)}</dd>
        <dt>{t(locale,"sim.bot.valued_at")}</dt><dd>{botZonedTime(data.valuation.valued_at,locale,timeZone)}</dd>
        <dt>{t(locale,"sim.bot.evaluated_at")}</dt><dd>{botZonedTime(data.as_of,locale,timeZone)}</dd>
      </dl>
      {data.turnover.reason ? <p>{t(locale,"sim.bot.performance.turnover")} · {turnoverReasons[data.turnover.reason] ? t(locale,turnoverReasons[data.turnover.reason]) : data.turnover.reason}</p> : null}
      <p>{t(locale,"sim.bot.performance.turnover_basis")} · {botZonedTime(data.turnover.window_start,locale,timeZone)} → {botZonedTime(data.turnover.window_end,locale,timeZone)}</p>
      <p>{t(locale,"sim.bot.performance.token_scope")} · {botZonedTime(data.llm.first_run_at,locale,timeZone)} → {botZonedTime(data.llm.last_run_at,locale,timeZone)}</p>
      {data.history.truncated ? <p>{t(locale,"sim.bot.performance.truncated")}</p> : null}
      <p>{t(locale,"sim.bot.performance.basis")}</p><p>{t(locale,"sim.bot.performance.cost_unknown")}</p><p>{t(locale,"sim.bot.performance.deterministic_unavailable")}</p>
    </div> : null}
  </TmDrawer>;
}

export function PaperBotScheduleNotice({ config }: { readonly config: PaperBotConfig }) {
  const {locale}=useLocale();
  const issues=(config.schedule_observations ?? []).filter(row=>["missed","failed","blocked","partial"].includes(row.status));
  const today=issues.filter(row=>row.session_date === config.market.session_date);
  const previous=issues.filter(row=>row.session_date < config.market.session_date).sort((a,b)=>b.session_date.localeCompare(a.session_date))[0];
  return <div className="space-y-1" role="status">
    {today.map(row=><p key={row.slot} className="text-tm-warn">{row.session_date} · {botTriggerLabel(locale,row.slot)} · {t(locale,row.status === "missed" ? "sim.bot.schedule.missed" : row.status === "blocked" ? "sim.bot.schedule.blocked" : row.status === "partial" ? "sim.bot.status.partial" : "sim.bot.status.failed")}</p>)}
    {previous ? <p className="text-tm-muted">{t(locale,"sim.bot.schedule.historical_issue")} · {previous.session_date} · {botTriggerLabel(locale,previous.slot)} · {t(locale,previous.status === "missed" ? "sim.bot.schedule.missed" : previous.status === "blocked" ? "sim.bot.schedule.blocked" : previous.status === "partial" ? "sim.bot.status.partial" : "sim.bot.status.failed")}</p> : null}
  </div>;
}

export function PaperBotScheduleDrawer({ config, open, onClose, onRun }: { readonly config: PaperBotConfig; readonly open: boolean; readonly onClose: () => void; readonly onRun: (id: string) => void }) {
  const { locale }=useLocale();
  const { timeZone } = useTimezonePreference();
  const observations=config.schedule_observations ?? [];
  const statuses: Record<string,TranslationKey>={planned:"sim.bot.schedule.planned",waiting:"sim.bot.schedule.waiting",blocked:"sim.bot.schedule.blocked",missed:"sim.bot.schedule.missed",skipped:"sim.bot.status.skipped",queued:"sim.bot.status.queued",running:"sim.bot.status.running",completed:"sim.bot.status.completed",no_trade:"sim.bot.status.no_trade",partial:"sim.bot.status.partial",failed:"sim.bot.status.failed",stopped:"sim.bot.status.stopped",observed:"sim.bot.schedule.observed",dispatched:"sim.bot.schedule.dispatched",enqueued:"sim.bot.status.queued"};
  return <TmDrawer open={open} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={t(locale,"sim.bot.schedule_observations")} width="lg">
    <div className="space-y-4 text-xs leading-5 text-tm-muted"><p>{t(locale,"sim.bot.schedule_observation_hint")}</p>{config.readiness?.schedule_reason ? <p>{botReason(locale,config.readiness.schedule_reason)}</p> : null}
      {observations.length ? <ul className="divide-y divide-tm-rule">{observations.map((row,index)=><li key={`${row.session_date}-${row.slot}-${index}`} className="space-y-2 py-4">
        <div className="flex flex-wrap justify-between gap-2"><span className="font-tm-mono text-tm-fg">{row.session_date} · {row.slot.includes("open") ? t(locale,"sim.bot.open_trigger") : row.slot.includes("close") ? t(locale,"sim.bot.close_trigger") : t(locale,"sim.bot.schedule_trigger")}</span><span className={row.status === "missed" ? "text-tm-warn" : undefined}>{statuses[row.status] ? t(locale,statuses[row.status]) : row.status}</span></div>
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1"><dt>{t(locale,"sim.bot.planned_at")}</dt><dd>{botZonedTime(row.planned_at,locale,timeZone)}</dd><dt>{t(locale,"sim.bot.observed_at")}</dt><dd>{row.observed_at ? `${botZonedTime(row.observed_at,locale,timeZone)}` : "—"}</dd></dl>
        {row.reason ? <p>{botReason(locale,row.reason)}</p> : null}
        {row.inferred && row.status !== "planned" ? <p>{t(locale,"sim.bot.schedule.inferred")}</p> : null}
        {row.run_id ? <TmButton variant="secondary" size="xs" onClick={()=>onRun(row.run_id!)}>{t(locale,"sim.bot.source_run")}</TmButton> : null}
      </li>)}</ul> : <p>{t(locale,"sim.bot.no_schedule_observations")}</p>}
    </div>
  </TmDrawer>;
}
