"use client";

import { useState } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmDrawer } from "@/components/tm/TmDrawer";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { PaperApiError, type OrderOut } from "@/lib/api/paper";
import { type PaperBotRun, type PaperBotRunStatus } from "@/lib/api/paper-bot";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { Metric } from "./PaperUi";

export function botModelLabel(provider: string | null, model: string | null) {
  return model || provider || "—";
}

export function botRunLabel(locale: Locale, status: PaperBotRunStatus) {
  return t(locale, `sim.bot.status.${status}`);
}

export function botStageLabel(locale: Locale, run: PaperBotRun) {
  const keys: Record<string, TranslationKey> = {
    gathering: "sim.bot.stage.gathering", deciding: "sim.bot.stage.deciding",
    validating: "sim.bot.stage.validating", executing: "sim.bot.stage.executing",
    researching: "sim.bot.stage.researching", settling: "sim.bot.stage.settling",
    valuing: "sim.bot.stage.valuing",
  };
  return run.stage && keys[run.stage] ? t(locale, keys[run.stage]) : botRunLabel(locale, run.status);
}

export function botTriggerLabel(locale: Locale, trigger: string) {
  if (trigger === "manual") return t(locale, "sim.bot.manual");
  if (trigger.includes("open")) return t(locale, "sim.bot.open_trigger");
  if (trigger.includes("close")) return t(locale, "sim.bot.close_trigger");
  return t(locale, "sim.bot.schedule_trigger");
}

export function botTime(value: string | null | undefined, locale: Locale, zone = "Asia/Shanghai") {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    timeZone: zone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date);
}

const reasonKeys: Record<string, TranslationKey> = {
  market_closed:"sim.bot.reason.market_closed", near_close:"sim.bot.reason.near_close",
  credential_missing:"sim.bot.reason.credential_missing", storage_headroom_low:"sim.bot.reason.storage_headroom_low",
  account_inactive:"sim.bot.reason.account_inactive", daily_limit:"sim.bot.reason.daily_limit",
  run_active:"sim.bot.reason.run_active", research_unavailable:"sim.bot.reason.research_unavailable",
  research_stale:"sim.bot.reason.research_stale", schedule_paused:"sim.bot.reason.schedule_paused",
  schedule_disabled:"sim.bot.reason.schedule_paused", paused:"sim.bot.reason.schedule_paused",
  scheduled:"sim.bot.scheduled", no_slots_enabled:"sim.bot.reason.no_slots_enabled",
  keep_cash:"sim.bot.reason.keep_cash", keep_positions:"sim.bot.reason.keep_positions",
  strategy_no_op:"sim.bot.reason.strategy_no_op", evidence_insufficient:"sim.bot.reason.evidence_insufficient",
  config_changed:"sim.bot.reason.config_changed", execution_window_expired:"sim.bot.reason.execution_window_expired",
  decision_budget_exhausted:"sim.bot.reason.decision_budget_exhausted", model_timeout:"sim.bot.reason.model_timeout",
  invalid_output:"sim.bot.reason.invalid_output", research_budget_exhausted:"sim.bot.reason.research_budget_exhausted",
  output_truncated:"sim.bot.reason.output_truncated",
  execution_blocked:"sim.bot.reason.execution_blocked", targets_unchanged:"sim.bot.reason.targets_unchanged",
  execution_partial:"sim.bot.reason.execution_partial", orders_settled:"sim.bot.reason.orders_settled",
  stage_failed:"sim.bot.reason.stage_failed", dispatch_failed:"sim.bot.reason.dispatch_failed",
  targets_proposed:"sim.bot.reason.targets_proposed", orders_accepted:"sim.bot.reason.orders_accepted",
  account_unavailable:"sim.bot.reason.account_inactive", enqueue_failed:"sim.bot.reason.dispatch_failed", slot_expired:"sim.bot.reason.slot_expired",
  trigger_not_observed:"sim.bot.reason.trigger_not_observed", runner_dispatch_failed:"sim.bot.reason.dispatch_failed",
};

export function botReason(locale: Locale, reason: string | null | undefined) {
  if (!reason) return "—";
  return reasonKeys[reason] ? t(locale, reasonKeys[reason]) : reason;
}

export function PaperBotState({ error, loading, onRetry }: { readonly error?: unknown; readonly loading?: boolean; readonly onRetry?: () => void }) {
  const { locale } = useLocale();
  const auth = error instanceof PaperApiError && error.status === 401;
  return <div className="p-3">
    <TmStatePane state={loading ? "loading" : auth ? "unauthorized" : "error"} title={t(locale, loading ? "common.loading" : auth ? "sim.bot.auth" : "sim.bot.unavailable")} description={!loading && !auth ? t(locale, "sim.bot.unavailable_hint") : undefined} action={!loading && !auth && onRetry ? {label:t(locale,"sim.bot.retry"),onClick:onRetry} : undefined} className="border-0 !bg-transparent" />
    {!loading && !auth && error instanceof Error ? <details className="px-3 text-xs leading-5 text-tm-muted"><summary className="cursor-pointer">{t(locale,"sim.bot.diagnostics")}</summary><p className="mt-2 whitespace-pre-wrap break-words">{error.message}</p></details> : null}
    {auth ? <TmLinkButton href="/signin?callbackUrl=%2Fpaper%3Faccount%3Dbot">{t(locale,"sim.auth.cta")}</TmLinkButton> : null}
  </div>;
}

export function PaperBotPagination({ page, total, loading, onChange }: { readonly page: number; readonly total: number; readonly loading: boolean; readonly onChange: (page: number) => void }) {
  const { locale } = useLocale();
  return <TmPagination page={page} pageSize={5} totalItems={total} pageSizeOptions={[5]} onPageChange={onChange} onPageSizeChange={() => {}} loading={loading} labels={{navigation:t(locale,"sim.bot.pagination"),previous:t(locale,"sim.bot.previous"),previousAriaLabel:t(locale,"sim.bot.previous"),next:t(locale,"sim.bot.next_page"),nextAriaLabel:t(locale,"sim.bot.next_page"),page:(current,count)=>`${current} / ${count}`,pageSize:t(locale,"sim.bot.per_page"),total:n=>t(locale,"sim.bot.total").replace("{n}",String(n))}} />;
}

export function botRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

export function recordedBotActions(run: PaperBotRun) {
  const decision=botRecord(run.result?.decision);
  const planned=Array.isArray(decision?.actions) ? decision.actions.map(botRecord).filter((row): row is Record<string,unknown>=>row!==null) : [];
  const raw=run.result?.actions ?? run.result?.action_results ?? decision?.actions;
  return Array.isArray(raw) ? raw.map(botRecord).filter((row): row is Record<string,unknown>=>row!==null).map(action=>({...planned.find(plan=>plan.action_id === action.action_id),...action})) : [];
}

export function PaperBotOutcome({ run }: { readonly run: PaperBotRun }) {
  const { locale }=useLocale();
  const decision=botRecord(run.result?.decision);
  const reason=decision?.no_trade_reason ?? run.result?.outcome_reason;
  const active=run.status === "queued" || run.status === "running";
  const noActions=!recordedBotActions(run).length;
  return <div className="space-y-1 text-xs leading-5 text-tm-muted">
    {typeof reason === "string" && reason ? <p>{t(locale,"sim.bot.outcome_reason")} · {botReason(locale,reason)}</p> : null}
    {noActions && !active ? <p>{t(locale,"sim.bot.no_order_evidence")}</p> : null}
  </div>;
}

export function PaperBotOutputEvidence({ value }: { readonly value: unknown }) {
  const {locale}=useLocale();
  const output=botRecord(value);
  if(!output) return null;
  const statuses:Record<string,TranslationKey>={valid:"sim.bot.output.valid",truncated:"sim.bot.output.truncated",invalid_json:"sim.bot.output.invalid_json",schema_mismatch:"sim.bot.output.schema_mismatch",context_mismatch:"sim.bot.output.context_mismatch",output_size_exceeded:"sim.bot.output.too_large"};
  return <section className="space-y-2 text-xs text-tm-muted"><h3 className="font-semibold text-tm-fg">{t(locale,"sim.bot.output.title")}</h3><p>{t(locale,statuses[String(output.parse_status)] ?? "sim.bot.output.unknown")}</p><p>{t(locale,"sim.bot.output.stop")} · {String(output.finish_reason ?? "unknown")} · {String(output.completion_tokens ?? "—")} / {String(output.token_limit ?? "—")} tokens</p>{Array.isArray(output.fields) && output.fields.length ? <p className="break-words font-tm-mono">{output.fields.map(String).join(", ")}</p> : null}</section>;
}

export function PaperBotExecutionSummary({ run }: { readonly run: PaperBotRun }) {
  const {locale}=useLocale();
  const summary=run.order_summary;
  if(!summary) return <p className="text-xs text-tm-muted">{t(locale,"sim.bot.execution_unknown")}</p>;
  return <section aria-label={t(locale,"sim.bot.execution_summary")} className="space-y-3 border-y border-tm-rule py-3">
    <div className="flex items-center justify-between text-xs text-tm-muted"><span>{t(locale,"sim.bot.execution_summary")} · {summary.total}</span>{summary.cancelled>0 ? <span>{t(locale,"sim.bot.execution_cancelled")} {summary.cancelled}</span> : null}</div>
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <Metric label={t(locale,"sim.status.filled")} value={String(summary.filled)} />
      <Metric label={t(locale,"sim.status.pending")} value={String(summary.pending)} tone={summary.pending>0 ? "text-tm-warn" : "text-tm-fg"} />
      <Metric label={t(locale,"sim.bot.execution_failed")} value={String(summary.failed+summary.expired)} tone={summary.failed+summary.expired>0 ? "text-tm-neg" : "text-tm-fg"} />
      <Metric label={t(locale,"sim.bot.fee")} value={summary.paid_fees == null ? "—" : `$${summary.paid_fees.toFixed(2)}`} />
    </div>
  </section>;
}

/** Only render recorded actions. Unknown result shapes remain available in details. */
export function PaperBotActions({ run, limit, page }: { readonly run: PaperBotRun; readonly limit?: number; readonly page?: number }) {
  const { locale } = useLocale();
  const allActions=recordedBotActions(run);
  const actions=page != null ? allActions.slice((page-1)*5,page*5) : limit == null ? allActions : allActions.slice(0,limit);
  if(!actions.length) return null;
  const statusKeys: Record<string,TranslationKey> = {
    accepted:"sim.bot.order.accepted", rejected:"sim.bot.order.rejected", held:"sim.bot.action.held",
    deferred:"sim.bot.action.deferred", existing:"sim.bot.action.existing", cancel_requested:"sim.bot.order.cancel_requested",
    filled:"sim.status.filled", failed:"sim.status.failed", expired:"sim.bot.order.expired", cancelled:"sim.status.cancelled",
    pending_market_data:"sim.bot.order.pending_market_data", pending:"sim.bot.order.pending_market_data",
  };
  const reasons:Record<string,TranslationKey> = {
    ticker_has_pending_order:"sim.bot.reason.ticker_has_pending_order", awaiting_settled_cash:"sim.bot.reason.awaiting_settled_cash", bot_order_not_found:"sim.bot.reason.bot_order_not_found",
  };
  return <div className="space-y-2"><h3 className="text-xs font-semibold text-tm-muted">{t(locale,"sim.bot.actions")}</h3><ul className="divide-y divide-tm-rule border-y border-tm-rule">{actions.map((action,index)=>{
    const status=typeof action.status === "string" ? action.status : "";
    const orderStatus=typeof action.order_status === "string" ? action.order_status : null;
    const reason=typeof action.reason === "string" ? action.reason : "";
    const symbol=typeof action.ticker === "string" ? action.ticker : typeof action.instrument_id === "string" ? action.instrument_id : "—";
    return <li key={typeof action.action_id === "string" ? action.action_id : index} className="space-y-1 py-3 text-xs leading-5"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-tm-mono font-semibold text-tm-fg">{symbol}</span><span className={status === "rejected" || status === "failed" ? "text-tm-neg" : "text-tm-muted"}>{t(locale,"sim.bot.action_result")} · {t(locale,statusKeys[status] ?? "sim.bot.action.unknown")}</span></div><div className="flex flex-wrap gap-3 text-tm-fg-2">{action.side === "buy" || action.side === "sell" ? <span>{t(locale,action.side === "buy" ? "sim.order_side.buy" : "sim.order_side.sell")}{typeof action.qty === "number" ? ` · ${action.qty}` : ""}</span> : null}{typeof action.target_weight === "number" ? <span>{t(locale,"sim.bot.target")} {(action.target_weight*100).toFixed(1)}%</span> : null}{action.type === "cancel_order" ? <span>{t(locale,"sim.bot.action.cancel_order")}</span> : null}</div>{orderStatus ? <p className={orderStatus === "failed" || orderStatus === "rejected" ? "text-tm-neg" : "text-tm-fg-2"}>{t(locale,"sim.bot.actual_order_status")} · {t(locale,statusKeys[orderStatus] ?? "sim.bot.action.unknown")}{typeof action.filled_at === "string" ? ` · ${botTime(action.filled_at,locale)} CST` : ""}{typeof action.filled_price === "number" ? ` · $${action.filled_price.toFixed(2)}` : ""}{typeof action.fee === "number" ? ` · ${t(locale,"sim.bot.fee")} $${action.fee.toFixed(2)}` : ""}</p> : status === "accepted" ? <p>{t(locale,"sim.bot.order_status_unknown")}</p> : null}{reason ? <p className="break-words text-tm-muted">{reasons[reason] ? t(locale,reasons[reason]) : reason}</p> : null}</li>;
  })}</ul>{page == null && allActions.length>actions.length ? <p className="text-xs text-tm-muted">{t(locale,"sim.bot.more_actions").replace("{shown}",String(actions.length)).replace("{total}",String(allActions.length))}</p> : null}</div>;
}

export function PaperBotRunDrawer({ run, open, onClose, loading, error, onRetry }: { readonly run: PaperBotRun | null; readonly open?: boolean; readonly onClose: () => void; readonly loading?: boolean; readonly error?: unknown; readonly onRetry?: () => void }) {
  const { locale } = useLocale();
  const [tab,setTab]=useState<"overview" | "actions" | "reviews" | "evidence">("overview");
  const [actionPage,setActionPage]=useState(1);
  const [reviewPage,setReviewPage]=useState(1);
  const decision=botRecord(run?.result?.decision);
  const diagnostics=botRecord(run?.result?.diagnostics);
  const timings=botRecord(diagnostics?.stage_timings_ms ?? diagnostics?.stage_timings);
  const stages=Array.isArray(diagnostics?.stages) ? diagnostics.stages.map(botRecord).filter((stage): stage is Record<string,unknown>=>stage !== null) : [];
  const notes=Array.isArray(decision?.position_notes) ? decision.position_notes.map(botRecord).filter((note): note is Record<string,unknown>=>note!==null && typeof note.ticker === "string") : [];
  return <TmDrawer open={open ?? !!run} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={t(locale,"sim.bot.decision")} width="xl">
    {!run ? <PaperBotState loading={loading} error={error} onRetry={onRetry} /> : <div className="space-y-5 text-sm leading-6 text-tm-fg">
      {loading ? <p role="status" className="text-xs text-tm-muted">{t(locale,"sim.bot.refreshing_details")}</p> : error ? <div><p className="text-xs text-tm-warn">{t(locale,"sim.bot.details_stale")}</p><PaperBotState error={error} onRetry={onRetry} /></div> : null}
      <div className="flex flex-wrap gap-3 font-tm-mono text-xs text-tm-muted"><span>{botStageLabel(locale,run)}</span><span>{botTriggerLabel(locale,run.trigger)}</span><span>{botModelLabel(run.provider,run.model)}</span></div>
      <SegmentedTabs active={tab} onChange={setTab} ariaLabel={t(locale,"sim.bot.details")} items={[{key:"overview",label:t(locale,"sim.bot.run_overview")},{key:"actions",label:`${t(locale,"sim.bot.actions")} (${recordedBotActions(run).length})`},{key:"reviews",label:`${t(locale,"sim.bot.holding_review")} (${notes.length})`},{key:"evidence",label:t(locale,"sim.bot.run_diagnostics")}]} />
      {tab === "overview" ? <>
      <PaperBotExecutionSummary run={run} />
      <p className="whitespace-pre-wrap break-words">{run.summary || t(locale,"sim.bot.no_result")}</p>
      <PaperBotOutcome run={run} />
      {decision?.target_semantics === "patch_targets" ? <p className="text-xs text-tm-muted">{t(locale,"sim.bot.patch_targets")}</p> : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 font-tm-mono text-xs"><dt>{t(locale,"sim.bot.started")}</dt><dd>{run.started_at ? `${botTime(run.started_at,locale)} CST` : "—"}</dd><dt>{t(locale,"sim.bot.finished")}</dt><dd>{run.finished_at ? `${botTime(run.finished_at,locale)} CST` : "—"}</dd><dt>{t(locale,"sim.bot.tokens")}</dt><dd>{run.prompt_tokens == null && run.completion_tokens == null ? t(locale,"sim.bot.tokens_unknown") : `${run.prompt_tokens ?? "—"} / ${run.completion_tokens ?? "—"} tokens`}</dd></dl>
      </> : null}
      {tab === "actions" ? <><PaperBotActions run={run} page={actionPage} />{recordedBotActions(run).length ? <PaperBotPagination page={actionPage} total={recordedBotActions(run).length} loading={false} onChange={setActionPage} /> : <PaperBotOutcome run={run} />}</> : null}
      {tab === "reviews" ? notes.length ? <section><p className="text-xs text-tm-muted">{t(locale,"sim.bot.position_notes")}</p><ul className="divide-y divide-tm-rule">{notes.slice((reviewPage-1)*5,reviewPage*5).map((note,index)=><li key={index} className="space-y-1 py-3 text-sm leading-6"><span className="font-tm-mono font-semibold">{String(note.ticker)}</span>{(["note","thesis","invalidation","review_after"] as const).map(field=>typeof note[field] === "string" ? <p key={field} className="whitespace-pre-wrap break-words text-tm-muted">{field === "note" ? "" : `${t(locale,`sim.bot.position_${field}`)} · `}{String(note[field])}</p> : null)}</li>)}</ul><PaperBotPagination page={reviewPage} total={notes.length} loading={false} onChange={setReviewPage} /></section> : <p className="text-sm text-tm-muted">{t(locale,"sim.bot.review_missing")}</p> : null}
      {tab === "evidence" ? <>
      <PaperBotOutputEvidence value={diagnostics?.model_output} />
      {run.error ? <details><summary className="cursor-pointer text-tm-neg">{t(locale,"sim.bot.diagnostics")}</summary><p className="mt-2 whitespace-pre-wrap break-words text-xs text-tm-muted">{run.error}</p></details> : null}
      {timings ? <details><summary className="cursor-pointer text-xs">{t(locale,"sim.bot.stage_timings")}</summary><dl className="mt-2 grid grid-cols-[1fr_auto] gap-2 font-tm-mono text-xs text-tm-muted">{Object.entries(timings).map(([stage,value])=><div key={stage} className="contents"><dt>{botStageLabel(locale,{...run,stage})}</dt><dd>{typeof value === "number" ? `${value.toLocaleString()} ms` : "—"}</dd></div>)}</dl></details> : null}
      {stages.length ? <details><summary className="cursor-pointer text-xs">{t(locale,"sim.bot.stage_timings")}</summary><dl className="mt-2 grid grid-cols-[1fr_auto] gap-2 font-tm-mono text-xs text-tm-muted">{stages.map((stage,index)=><div key={index} className="contents"><dt>{typeof stage.stage === "string" ? botStageLabel(locale,{...run,stage:stage.stage}) : "—"}</dt><dd>{typeof stage.duration_ms === "number" ? `${stage.duration_ms.toLocaleString()} ms` : "—"}</dd></div>)}</dl></details> : null}
      {run.result ? <details><summary className="cursor-pointer">{t(locale,"sim.bot.result")}</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words font-tm-mono text-xs text-tm-muted">{JSON.stringify(run.result,null,2)}</pre></details> : null}
      </> : null}
    </div>}
  </TmDrawer>;
}

export function PaperBotOrderDrawer({ order, onClose, onRun }: { readonly order: OrderOut | null; readonly onClose: () => void; readonly onRun: (runId: string) => void }) {
  const { locale } = useLocale();
  const price=(value:number | null | undefined)=>value == null ? "—" : `$${value.toFixed(2)}`;
  return <TmDrawer open={!!order} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={order ? `${order.ticker} · #${order.id}` : t(locale,"sim.bot.orders")} width="lg">
    {order ? <div className="space-y-5 text-xs leading-5 text-tm-muted">
      <div className="flex flex-wrap items-center gap-4 text-sm text-tm-fg"><span>{t(locale,order.side === "buy" ? "sim.order_side.buy" : "sim.order_side.sell")} · {order.qty}</span><span>{["pending","filled","failed","cancelled"].includes(order.status) ? t(locale,`sim.status.${order.status}` as "sim.status.filled") : order.status === "expired" ? t(locale,"sim.bot.order.expired") : t(locale,"sim.bot.action.unknown")}</span></div>
      <p>{t(locale,"sim.bot.execution_note")}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 font-tm-mono">
        <dt>{t(locale,"sim.bot.accepted_at")}</dt><dd>{order.accepted_at ? `${botTime(order.accepted_at,locale)} CST` : "—"}</dd>
        <dt>{t(locale,"sim.bot.filled_at")}</dt><dd>{order.filled_at ? `${botTime(order.filled_at,locale)} CST` : "—"}</dd>
        <dt>{t(locale,"sim.bot.reference_price")}</dt><dd>{price(order.reference_price)}</dd>
        <dt>{t(locale,"sim.bot.fill_price")}</dt><dd>{price(order.fill_price)}</dd>
        <dt>{t(locale,"sim.bot.fee")}</dt><dd>{price(order.transaction_cost)}{order.fee_bps == null ? "" : ` · ${order.fee_bps} bps`}</dd>
        <dt>{t(locale,"sim.bot.slippage")}</dt><dd>{order.slippage_bps == null ? "—" : `${order.slippage_bps} bps`}</dd>
      </dl>
      {order.bot_run_id ? <TmButton variant="secondary" onClick={()=>onRun(order.bot_run_id!)}>{t(locale,"sim.bot.source_run")}</TmButton> : null}
      {order.fail_reason ? <p role="status" className="break-words text-tm-warn">{order.fail_reason}</p> : null}
      {order.execution_evidence ? <details><summary className="cursor-pointer">{t(locale,"sim.bot.execution_evidence")}</summary><pre className="mt-2 whitespace-pre-wrap break-words font-tm-mono">{JSON.stringify(order.execution_evidence,null,2)}</pre></details> : null}
    </div> : null}
  </TmDrawer>;
}
