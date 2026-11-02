"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmDrawer } from "@/components/tm/TmDrawer";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { PaperApiError, type OrderOut } from "@/lib/api/paper";
import { type PaperBotRun, type PaperBotRunStatus } from "@/lib/api/paper-bot";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

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

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

/** Only render recorded actions. Unknown result shapes remain available in details. */
export function PaperBotActions({ run }: { readonly run: PaperBotRun }) {
  const { locale } = useLocale();
  const result=run.result;
  const decision=record(result?.decision);
  const planned=Array.isArray(decision?.actions) ? decision.actions.map(record).filter((row): row is Record<string,unknown>=>row!==null) : [];
  const raw=result?.actions ?? result?.action_results ?? decision?.actions;
  const actions=Array.isArray(raw) ? raw.map(record).filter((row): row is Record<string,unknown>=>row!==null).slice(0,20).map(action=>({...planned.find(plan=>plan.action_id === action.action_id),...action})) : [];
  if(!actions.length) return null;
  const statusKeys: Record<string,TranslationKey> = {
    accepted:"sim.bot.order.accepted", rejected:"sim.bot.order.rejected", held:"sim.bot.action.held",
    deferred:"sim.bot.action.deferred", existing:"sim.bot.action.existing", cancel_requested:"sim.bot.order.cancel_requested",
    filled:"sim.status.filled", failed:"sim.status.failed", expired:"sim.bot.order.expired", cancelled:"sim.status.cancelled",
  };
  const reasons:Record<string,TranslationKey> = {
    ticker_has_pending_order:"sim.bot.reason.ticker_has_pending_order", awaiting_settled_cash:"sim.bot.reason.awaiting_settled_cash", bot_order_not_found:"sim.bot.reason.bot_order_not_found",
  };
  return <div className="space-y-2"><h3 className="text-xs font-semibold text-tm-muted">{t(locale,"sim.bot.actions")}</h3><ul className="divide-y divide-tm-rule border-y border-tm-rule">{actions.map((action,index)=>{
    const status=typeof action.status === "string" ? action.status : "";
    const reason=typeof action.reason === "string" ? action.reason : "";
    const symbol=typeof action.ticker === "string" ? action.ticker : typeof action.instrument_id === "string" ? action.instrument_id : "—";
    return <li key={typeof action.action_id === "string" ? action.action_id : index} className="space-y-1 py-3 text-xs leading-5"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-tm-mono font-semibold text-tm-fg">{symbol}</span><span className={status === "rejected" || status === "failed" ? "text-tm-neg" : "text-tm-muted"}>{t(locale,statusKeys[status] ?? "sim.bot.action.unknown")}</span></div><div className="flex flex-wrap gap-3 text-tm-fg-2">{action.side === "buy" || action.side === "sell" ? <span>{t(locale,action.side === "buy" ? "sim.order_side.buy" : "sim.order_side.sell")}{typeof action.qty === "number" ? ` · ${action.qty}` : ""}</span> : null}{typeof action.target_weight === "number" ? <span>{t(locale,"sim.bot.target")} {(action.target_weight*100).toFixed(1)}%</span> : null}{action.type === "cancel_order" ? <span>{t(locale,"sim.bot.action.cancel_order")}</span> : null}</div>{reason ? <p className="break-words text-tm-muted">{reasons[reason] ? t(locale,reasons[reason]) : reason}</p> : null}</li>;
  })}</ul></div>;
}

export function PaperBotRunDrawer({ run, onClose }: { readonly run: PaperBotRun | null; readonly onClose: () => void }) {
  const { locale } = useLocale();
  const decision=record(run?.result?.decision);
  const notes=Array.isArray(decision?.position_notes) ? decision.position_notes.map(record).filter((note): note is Record<string,unknown>=>note!==null && typeof note.ticker === "string" && typeof note.note === "string").slice(0,20) : [];
  return <TmDrawer open={!!run} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={t(locale,"sim.bot.decision")} width="lg">
    {run ? <div className="space-y-5 text-sm leading-6 text-tm-fg">
      <div className="flex flex-wrap gap-3 font-tm-mono text-xs text-tm-muted"><span>{botRunLabel(locale,run.status)}</span><span>{botTriggerLabel(locale,run.trigger)}</span><span>{run.provider} / {run.model}</span></div>
      <p className="whitespace-pre-wrap break-words">{run.summary || t(locale,"sim.bot.no_result")}</p>
      <PaperBotActions run={run} />
      {notes.length ? <section><h3 className="mb-2 text-xs font-semibold text-tm-muted">{t(locale,"sim.bot.position_notes")}</h3><ul className="divide-y divide-tm-rule">{notes.map((note,index)=><li key={index} className="py-2"><span className="font-tm-mono text-xs font-semibold">{String(note.ticker)}</span><p className="mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-tm-muted">{String(note.note)}</p></li>)}</ul></section> : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2 font-tm-mono text-xs"><dt>{t(locale,"sim.bot.started")}</dt><dd>{botTime(run.started_at,locale)} CST</dd><dt>{t(locale,"sim.bot.finished")}</dt><dd>{botTime(run.finished_at,locale)} CST</dd><dt>{t(locale,"sim.bot.tokens")}</dt><dd>{run.prompt_tokens == null && run.completion_tokens == null ? t(locale,"sim.bot.tokens_unknown") : `${run.prompt_tokens ?? "—"} / ${run.completion_tokens ?? "—"} tokens`}</dd></dl>
      {run.error ? <details><summary className="cursor-pointer text-tm-neg">{t(locale,"sim.bot.diagnostics")}</summary><p className="mt-2 whitespace-pre-wrap break-words text-xs text-tm-muted">{run.error}</p></details> : null}
      {run.result ? <details><summary className="cursor-pointer">{t(locale,"sim.bot.result")}</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words font-tm-mono text-xs text-tm-muted">{JSON.stringify(run.result,null,2)}</pre></details> : null}
    </div> : null}
  </TmDrawer>;
}

export function PaperBotOrderDrawer({ order, onClose, onRun }: { readonly order: OrderOut | null; readonly onClose: () => void; readonly onRun: (runId: string) => void }) {
  const { locale } = useLocale();
  const price=(value:number | null | undefined)=>value == null ? "—" : `$${value.toFixed(2)}`;
  return <TmDrawer open={!!order} onClose={onClose} closeLabel={t(locale,"sim.bot.close")} title={order ? `${order.ticker} · #${order.id}` : t(locale,"sim.bot.orders")} width="lg">
    {order ? <div className="space-y-5 text-xs leading-5 text-tm-muted">
      <p>{t(locale,"sim.bot.execution_note")}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 font-tm-mono">
        <dt>{t(locale,"sim.bot.accepted_at")}</dt><dd>{botTime(order.accepted_at,locale)} CST</dd>
        <dt>{t(locale,"sim.bot.filled_at")}</dt><dd>{botTime(order.filled_at,locale)} CST</dd>
        <dt>{t(locale,"sim.bot.reference_price")}</dt><dd>{price(order.reference_price)}</dd>
        <dt>{t(locale,"sim.bot.fill_price")}</dt><dd>{price(order.fill_price)}</dd>
        <dt>{t(locale,"sim.bot.fee")}</dt><dd>{price(order.transaction_cost)}{order.fee_bps == null ? "" : ` · ${order.fee_bps} bps`}</dd>
        <dt>{t(locale,"sim.bot.slippage")}</dt><dd>{order.slippage_bps == null ? "—" : `${order.slippage_bps} bps`}</dd>
      </dl>
      {order.bot_run_id ? <TmButton variant="secondary" onClick={()=>onRun(order.bot_run_id!)}>{t(locale,"sim.bot.source_run")}</TmButton> : null}
      {order.fail_reason || order.execution_evidence ? <details><summary className="cursor-pointer">{t(locale,"sim.bot.diagnostics")}</summary>{order.fail_reason ? <p className="mt-2 break-words">{order.fail_reason}</p> : null}{order.execution_evidence ? <pre className="mt-2 whitespace-pre-wrap break-words font-tm-mono">{JSON.stringify(order.execution_evidence,null,2)}</pre> : null}</details> : null}
    </div> : null}
  </TmDrawer>;
}
