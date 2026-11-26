"use client";

import Link from "next/link";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { fetchPicks, type PicksResponse } from "@/lib/api/picks";
import { useFactorMode } from "@/hooks/useFactorMode";
import {
  PAPER_SHORTLIST_SIZE,
  RECOMMENDATION_BOARD_SIZE,
  pickOrderSource,
  readPaperPickQuery,
  resolvePaperPick,
} from "../paper-order-source";
import {
  PaperApiError,
  cancelOrder,
  fetchAttribution,
  fetchEquityCurve,
  fetchOrders,
  fetchPaperAccount,
  fetchL2Summary,
  resetAccount,
  type AccountResponse,
  type EquityCurveResponse,
  type OrderOut,
  type TickerAttribution,
  type L2Summary,
} from "@/lib/api/paper";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmButton, TmDisclosureButton, TmLinkButton } from "@/components/tm/TmButton";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { shouldChartPaperCurve } from "@/lib/paper-curve";
import { TmStatePane } from "@/components/tm/TmStatePane";
import SimOrderForm from "../SimOrderForm";
import { Metric, TwoStepConfirm } from "./PaperUi";
import PaperRecommendations from "./PaperRecommendations";
import PaperPositionsWithSource from "./PaperPositionsWithSource";
import PaperCurvePane from "./PaperCurvePane";
import PaperSourceSummary from "./PaperSourceSummary";
import PaperOrdersPane from "./PaperOrdersPane";
import PaperL2Evidence from "./PaperL2Evidence";
import RecommendationPerformance from "../RecommendationPerformance";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import PaperBotScreen from "./PaperBotScreen";
import "./paper-bot.css";

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export default function PaperScreen() {
  const { locale } = useLocale();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [preferredMode] = useFactorMode();
  const pickQuery = readPaperPickQuery(searchParams, preferredMode);
  const kind = searchParams.get("account") === "bot" ? "bot" : "human";
  const accountTabs = <SegmentedTabs<"human" | "bot"> className="paper-account-tabs shrink-0" active={kind} ariaLabel={t(locale, "sim.accounts.label")} items={[{key:"human",label:t(locale,"sim.accounts.human")},{key:"bot",label:t(locale,"sim.accounts.bot")}]} onChange={next => {
    const query = new URLSearchParams(searchParams.toString());
    query.set("account", next);
    if (next === "bot") {
      for (const key of ["ticker", "mode", "side", "run", "date"]) query.delete(key);
    }
    router.replace(`${pathname}?${query}`, { scroll: false });
  }} />;
  const query = searchParams.toString();
  return kind === "bot" ? <PaperBotScreen accountTabs={accountTabs} /> : (
    <HumanPaperScreen
      key={`${pickQuery.mode}:${query}`}
      accountTabs={accountTabs}
      pickQuery={pickQuery}
      returnUrl={query ? `${pathname}?${query}` : pathname}
    />
  );
}

function HumanPaperScreen({ accountTabs, pickQuery, returnUrl }: {
  readonly accountTabs: ReactNode;
  readonly pickQuery: ReturnType<typeof readPaperPickQuery>;
  readonly returnUrl: string;
}) {
  const { locale } = useLocale();
  const { ticker, mode, side } = pickQuery;
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [orders, setOrders] = useState<readonly OrderOut[]>([]);
  const [curve, setCurve] = useState<EquityCurveResponse | null>(null);
  const [attribution, setAttribution] = useState<readonly TickerAttribution[]>([]);
  const [l2Summary, setL2Summary] = useState<L2Summary | null>(null);
  const [snapshot, setSnapshot] = useState<PicksResponse | null>(null);
  // Undefined follows the deep link or initial shortlist. Null clears the ticket.
  const [selection, setSelection] = useState<string | null | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [paperError, setPaperError] = useState<string | null>(null);
  const [resourceErrors, setResourceErrors] = useState<Partial<Record<"picks" | "account" | "orders" | "curve" | "attribution" | "l2", string>>>({});
  const [guideOpen, setGuideOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const orderTicket = useRef<HTMLDivElement>(null);
  const loadGeneration = useRef(0);
  const mounted = useRef(false);

  const loadAll = useCallback(async (showLoading = true) => {
    if (!mounted.current) return;
    const generation = ++loadGeneration.current;
    if (showLoading) setLoading(true);
    setRefreshing(true);
    setPaperError(null);
    const [picksResult, accountResult, ordersResult, curveResult, attributionResult, l2Result] = await Promise.allSettled([
      fetchPicks(ticker ? RECOMMENDATION_BOARD_SIZE : PAPER_SHORTLIST_SIZE, undefined, mode, side),
      fetchPaperAccount(),
      fetchOrders({ limit: 20 }),
      fetchEquityCurve(),
      fetchAttribution(),
      fetchL2Summary(),
    ]);
    if (generation !== loadGeneration.current) return;

    const nextErrors: typeof resourceErrors = {};
    const reason = (value: unknown) => value instanceof Error ? value.message : String(value);

    if (picksResult.status === "fulfilled") setSnapshot(picksResult.value);
    else nextErrors.picks = reason(picksResult.reason);
    if (accountResult.status === "fulfilled") {
      setAccount(accountResult.value);
      setAuthRequired(false);
    } else if (accountResult.reason instanceof PaperApiError && accountResult.reason.status === 401) {
      setAuthRequired(true);
      setAccount(null);
    } else {
      setAuthRequired(false);
      const accountError = accountResult.reason instanceof Error ? accountResult.reason.message : String(accountResult.reason);
      setPaperError(accountError);
      nextErrors.account = accountError;
    }
    if (ordersResult.status === "fulfilled") setOrders(ordersResult.value.orders);
    else nextErrors.orders = reason(ordersResult.reason);
    if (curveResult.status === "fulfilled") setCurve(curveResult.value);
    else nextErrors.curve = reason(curveResult.reason);
    if (attributionResult.status === "fulfilled") setAttribution(attributionResult.value.tickers);
    else nextErrors.attribution = reason(attributionResult.reason);
    if (l2Result.status === "fulfilled") setL2Summary(l2Result.value);
    else nextErrors.l2 = reason(l2Result.reason);
    setResourceErrors(nextErrors);
    setLoading(false);
    setRefreshing(false);
  }, [mode, side, ticker]);

  useEffect(() => {
    mounted.current = true;
    void loadAll();
    return () => {
      mounted.current = false;
      ++loadGeneration.current;
    };
  }, [loadAll]);

  const picksRun = snapshot?.run;
  const board = snapshot ? resolvePaperPick(snapshot, pickQuery, null) : null;
  const picksFrozen = board?.status === "frozen" || board?.status === "mode_unavailable";
  const ticket = snapshot ? resolvePaperPick(snapshot, pickQuery, selection) : null;
  const selectedPick = ticket?.status === "ready" ? ticket.pick : null;
  const selectedSource = selectedPick ? pickOrderSource(selectedPick, side) : null;
  const picks = snapshot?.picks.slice(0, PAPER_SHORTLIST_SIZE) ?? [];
  if (selectedPick && !picks.some(pick => pick.ticker === selectedPick.ticker)) picks.push(selectedPick);

  async function handleCancel(orderId: number) {
    await cancelOrder(orderId);
    await loadAll(false);
  }

  async function handleReset() {
    await resetAccount();
    await loadAll(false);
  }

  const totalReturn = account?.total_return_pct;
  const zh = locale === "zh";
  const accountUnavailable = authRequired || !!resourceErrors.account || !account;
  const modeLabel = mode === "long" ? (zh ? "战略" : "Strategic") : (zh ? "战术" : "Tactical");
  const boardLabel = side === "short" ? (zh ? " · 偏空榜" : " · Bearish board") : "";
  const picksHref = `/picks?mode=${mode}&side=${side}`;
  const showOrderTicket = () => {
    orderTicket.current?.scrollIntoView({ block: "center" });
    orderTicket.current?.focus({ preventScroll: true });
  };

  return (
    <TmScreen className="overflow-y-auto">
      <WorkbenchHeader
        eyebrow={locale === "zh" ? "每日工作流 · 组合执行" : "Daily workflow · Portfolio execution"}
        title={zh ? t(locale, "sim.page_title") : "Paper trading"}
        subtitle={zh ? "选择推荐、提交模拟单，再回看持仓与收益。" : "Select a recommendation, place a paper order, then review positions and returns."}
        statuses={[
          { label: zh ? "账户状态" : "Account", value: loading ? (zh ? "读取中" : "Loading") : authRequired ? (zh ? "需登录" : "Sign in") : paperError ? (zh ? "待重试" : "Retry needed") : account ? (zh ? "就绪" : "Ready") : "—", tone: paperError ? "negative" : account ? "positive" : "warning" },
          { label: zh ? "持仓 / 待成交" : "Positions / pending", value: accountUnavailable ? "—" : `${account.positions.length} / ${account.pending_orders}` },
          { label: locale === "zh" ? "推荐来源" : "Pick source", value: picksRun ? `${modeLabel} · RUN #${picksRun.run_id}${boardLabel}` : "—", tone: picksFrozen ? "warning" : picksRun ? "positive" : "default" },
        ]}
        action={<TmButton variant="secondary" loading={refreshing} loadingLabel={zh ? "更新中" : "Updating"} onClick={() => void loadAll(false)}>{zh ? "刷新账户" : "Refresh account"}</TmButton>}
      />
      {accountTabs}
      <TmPane
        title={locale === "zh" ? "账户概览" : "Account overview"}
        meta={
          <TmButton variant="ghost" aria-expanded={guideOpen} aria-controls="paper-account-help" onClick={() => setGuideOpen(open => !open)}>{zh ? "账户与规则" : "Account & rules"}</TmButton>
        }
      >
        <div className="grid grid-cols-2 gap-4 px-6 py-4 sm:grid-cols-4">
          <Metric label={t(locale, "sim.account.nav")} value={!accountUnavailable && account.portfolio_value !== null ? `$${FMT.format(account.portfolio_value)}` : "—"} />
          <Metric label={t(locale, "sim.account.cash")} value={!accountUnavailable ? `$${FMT.format(account.available_cash)}` : "—"} />
          <Metric label={t(locale, "sim.account.unrealized")} value={!accountUnavailable && account.unrealized_pnl !== null ? `${account.unrealized_pnl > 0 ? "+" : account.unrealized_pnl < 0 ? "-" : ""}$${FMT.format(Math.abs(account.unrealized_pnl))}` : "—"} tone={accountUnavailable || !account.unrealized_pnl ? "text-tm-fg" : account.unrealized_pnl > 0 ? "text-tm-pos" : "text-tm-neg"} />
          <Metric label={t(locale, "sim.workspace.total_return")} value={!accountUnavailable && totalReturn != null ? `${totalReturn > 0 ? "+" : ""}${totalReturn.toFixed(2)}%` : "—"} tone={accountUnavailable || !totalReturn ? "text-tm-fg" : totalReturn > 0 ? "text-tm-pos" : "text-tm-neg"} />
        </div>
        {guideOpen ? (
          <div id="paper-account-help" className="flex flex-wrap items-center justify-between gap-4 border-t border-tm-rule px-6 py-3 text-xs leading-5 text-tm-muted">
            <div><p>{t(locale, "sim.workspace.disclosure")}</p><p>{t(locale, "sim.workspace.source_note")}</p>{!accountUnavailable && account.reserved_cash > 0 ? <p>{zh ? "待成交订单预留现金" : "Cash reserved for pending orders"} ${FMT.format(account.reserved_cash)}</p> : null}</div>
            {!accountUnavailable ? <TwoStepConfirm idleLabel={t(locale, "sim.reset_btn")} warnText={t(locale, "sim.reset_confirm")} doneText={t(locale, "sim.reset_done")} onConfirm={handleReset} /> : null}
          </div>
        ) : null}
      </TmPane>

      {picksFrozen ? <FrozenRecommendations /> : null}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane
          className="min-w-0 lg:border-r lg:border-tm-rule"
          title={zh ? "今日推荐 · 选择标的" : "Today's picks · Select a ticker"}
          meta={
            <span className="flex flex-wrap items-center gap-3"><span>{picksRun ? `${picksRun.market_date} · RUN #${picksRun.run_id}` : "—"}</span><TmLinkButton href={picksHref}>{zh ? "全部推荐" : "All picks"}</TmLinkButton></span>
          }
        >
          {resourceErrors.picks ? <SectionError detail={resourceErrors.picks} onRetry={() => void loadAll(false)} /> : null}
          {loading && picks.length === 0 ? <Loading /> : <PaperRecommendations picks={picks} selectedTicker={selectedPick?.ticker ?? null} actionable={!picksFrozen && !refreshing && !resourceErrors.picks} onSelect={(pick) => setSelection(pick.ticker)} />}
        </TmPane>
        <TmPane className="min-w-0" title={t(locale, "sim.workspace.order_title")} meta={selectedPick ? <TmButton variant="ghost" onClick={() => setSelection(null)}>{t(locale, "sim.workspace.clear")}</TmButton> : undefined}>
          <div ref={orderTicket} tabIndex={-1} aria-label={zh ? "模拟下单区" : "Paper order ticket"} className="px-4 py-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-tm-accent">
            {loading ? <Loading />
              : resourceErrors.picks ? <p className="py-6 text-sm text-tm-muted">{zh ? "请先重试读取来源推荐。" : "Retry the recommendation panel to load the source snapshot."}</p>
              : ticket?.status === "frozen" ? <OrderingPaused market={picksRun?.market_date ?? null} picksHref={picksHref} />
              : ticket && ticket.status !== "ready" && ticket.status !== "unselected" ? (
                <PickTicketStatus status={ticket.status} ticker={ticker} />
              ) : authRequired ? <AuthPrompt hint={t(locale, "sim.workspace.order_auth")} cta={t(locale, "sim.auth.cta")} returnUrl={returnUrl} />
              : paperError ? <PaperError detail={paperError} />
              : selectedPick && selectedSource && account ? (
                <SimOrderForm
                  key={`${selectedSource.runId}:${selectedSource.ticker}`}
                  layout="ticket"
                  disabled={refreshing}
                  fixedTicker={selectedPick.ticker}
                  locale={locale}
                  onPlaced={() => { void loadAll(false); }}
                  pickSource={selectedSource}
                  latestPrice={selectedPick.latest_price}
                  priceDate={selectedPick.price_date}
                  availableCash={account.available_cash}
                  portfolioValue={account.portfolio_value ?? undefined}
                  targetWeight={0.02}
                  initialSide={selectedPick.rating === "SELL" || selectedPick.rating === "UW" ? "sell" : "buy"}
                />
              ) : <p className="py-6 text-sm leading-6 text-tm-muted">{zh ? "从左侧选择一个标的，核对数量后再提交模拟单。" : "Choose a ticker on the left, then review the quantity before submitting."}</p>}
          </div>
        </TmPane>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane className="min-w-0 lg:border-r lg:border-tm-rule" title={t(locale, "sim.workspace.positions")} meta={accountUnavailable ? "—" : `${account.positions.length} ${zh ? "个标的" : "positions"}`}>
          {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} returnUrl={returnUrl} /> : resourceErrors.account ? <SectionError detail={resourceErrors.account} onRetry={() => void loadAll(false)} /> : account ? <>
            {resourceErrors.attribution ? <SectionError detail={resourceErrors.attribution} onRetry={() => void loadAll(false)} /> : null}
            <PaperPositionsWithSource positions={account.positions} attribution={attribution} attributionAvailable={!resourceErrors.attribution} pendingOrders={account.pending_orders} onChoose={picksFrozen ? undefined : showOrderTicket} chooseDisabledReason={picksFrozen ? (zh ? "推荐快照暂不可交易，下单区已暂停；见页面顶部的快照状态。" : "The recommendation snapshot is not tradable, so the order ticket is paused; see the snapshot status at the top.") : undefined} />
          </> : null}
        </TmPane>
        <TmPane className="min-w-0" title={zh ? "我的模拟净值" : "My paper equity"} meta={curve?.base_date ?? (zh ? "按日估值" : "Daily marks")}>
          {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} returnUrl={returnUrl} /> : resourceErrors.curve ? <SectionError detail={resourceErrors.curve} onRetry={() => void loadAll(false)} /> : shouldChartPaperCurve(account) ? <PaperCurvePane curve={curve} compact showDisclaimer={false} /> : <TmStatePane state="empty" title={zh ? "尚无持仓，暂不比较收益" : "No holdings yet, so no return comparison"} description={zh ? "账户一直是现金，净值固定在起点。产生持仓后才与 SPY 在同一起点比较。" : "The account has only held cash, so its value is flat by construction. SPY is compared once a position exists."} className="!min-h-[148px] rounded-none border-0 !bg-transparent" />}
          {!loading && !authRequired ? <><TmDisclosureButton expanded={sourceOpen} onClick={() => setSourceOpen(v => !v)} aria-controls="paper-source-details" label={t(locale, "sim.workspace.source_record")} />{sourceOpen ? <div id="paper-source-details">{resourceErrors.attribution ? <SectionError detail={resourceErrors.attribution} onRetry={() => void loadAll(false)} /> : <PaperSourceSummary rows={attribution} />}</div> : null}</> : null}
        </TmPane>
      </div>

      <TmPane title={t(locale, "sim.workspace.recent_orders")} meta={zh ? "最近 20 笔 · 市价单下一交易日收盘撮合" : "Latest 20 · Market orders fill at the next session's close"}>
        {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} returnUrl={returnUrl} /> : resourceErrors.orders ? <SectionError detail={resourceErrors.orders} onRetry={() => void loadAll(false)} /> : <PaperOrdersPane orders={orders} onCancel={handleCancel} attribution={attribution} attributionStatus={resourceErrors.attribution ? "unavailable" : "ready"} showAttribution={false} showDisclaimer={false} />}
      </TmPane>
      <div>
        <TmDisclosureButton expanded={researchOpen} onClick={() => setResearchOpen(v => !v)} aria-controls="paper-system-evidence" label={zh ? "系统策略验证" : "System policy validation"} meta={zh ? "独立研究账户，不计入我的收益" : "Independent research books, excluded from my returns"} />
        {researchOpen ? <div id="paper-system-evidence"><RecommendationPerformance /><TmDisclosureButton expanded={ledgerOpen} onClick={() => setLedgerOpen(v => !v)} aria-controls="paper-ledger-details" label={zh ? "账本状态与历史异常" : "Book status & historical exceptions"} />{ledgerOpen ? <div id="paper-ledger-details">{resourceErrors.l2 ? <SectionError detail={resourceErrors.l2} onRetry={() => void loadAll(false)} /> : <PaperL2Evidence summary={l2Summary} />}</div> : null}</div> : null}
      </div>
    </TmScreen>
  );
}

function Loading() {
  const { locale } = useLocale();
  return <div className="px-3 py-10 font-tm-mono text-xs text-tm-muted">{t(locale, "common.loading")}</div>;
}

function AuthPrompt({ hint, cta, returnUrl }: {
  readonly hint: string;
  readonly cta: string;
  readonly returnUrl: string;
}) {
  return <div className="flex flex-col items-start gap-3 px-3 py-8"><p className="font-tm-mono text-xs text-tm-muted">{hint}</p><Link href={`/signin?${new URLSearchParams({ callbackUrl: returnUrl })}`} className="border border-tm-accent px-3 py-1.5 font-tm-mono text-xs text-tm-accent hover:bg-tm-accent hover:text-tm-bg">{cta}</Link></div>;
}

function PaperError({ detail }: { readonly detail: string }) {
  const { locale } = useLocale();
  void detail;
  return <p className="font-tm-mono text-xs leading-5 text-tm-neg">{t(locale, "sim.load_error_hint")}</p>;
}

function SectionError({ detail, onRetry }: { readonly detail: string; readonly onRetry: () => void }) {
  const { locale } = useLocale();
  const authRequired = /authorization|authentication|unauthorized|\b401\b/i.test(detail);
  const message = authRequired
    ? (locale === "zh" ? "登录后可查看该区块，当前未将未知数据显示为空记录。" : "Sign in to view this section; unknown data is not shown as an empty record.")
    : (locale === "zh" ? "该区块暂时无法确认，未将其显示为零。" : "This section is unavailable; unknown data is not shown as zero.");
  return <div role={authRequired ? "status" : "alert"} className={`m-3 flex items-center justify-between gap-3 border px-3 py-2 font-tm-mono text-xs ${authRequired ? "border-tm-rule bg-tm-bg-2 text-tm-muted" : "border-tm-neg/40 bg-tm-neg/10 text-tm-neg"}`}><span>{message}</span><TmButton type="button" onClick={onRetry} variant={authRequired ? "secondary" : "danger"} size="xs">{locale === "zh" ? "重新检查" : "Check again"}</TmButton></div>;
}

function FrozenRecommendations() {
  const { locale } = useLocale();
  return <p role="status" className="mx-4 my-3 rounded-[2px] border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 font-tm-mono text-xs leading-5 text-tm-neg">{t(locale, "picks.stale_freeze_banner")}</p>;
}

function PickTicketStatus({ status, ticker }: {
  readonly status: "invalid" | "mode_unavailable" | "superseded" | "not_ranked" | "no_close";
  readonly ticker: string | null;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const message = {
    invalid: zh ? "此推荐链接无效，请从推荐页重新打开。" : "This recommendation link is invalid. Open a new ticket from Picks.",
    mode_unavailable: zh ? "当前快照没有该推荐模式，暂时无法下单。" : "This recommendation mode is unavailable in the current snapshot.",
    superseded: zh ? "来源快照已过期或被替换，请核对当前推荐后重新选择。" : "The source snapshot has expired or been superseded. Review the current picks before selecting again.",
    not_ranked: zh ? `${ticker} 不在来源榜单中，请重新选择。` : `${ticker} is not in the source board. Select a current pick.`,
    no_close: zh ? `${ticker} 缺少快照交易日的有效收盘价，暂时无法下单。` : `${ticker}'s close is unavailable for the snapshot session.`,
  }[status];
  return <p role="status" className="py-6 text-sm leading-6 text-tm-muted">{message}</p>;
}

function OrderingPaused({ market, picksHref }: {
  readonly market: string | null;
  readonly picksHref: string;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return <div className="space-y-2 py-4 text-sm leading-6 text-tm-muted">
    <p className="text-tm-fg-2">{zh ? "下单区已暂停" : "Order ticket paused"}</p>
    <p>{zh ? `当前推荐快照（市场日 ${market ?? "—"}）未对齐最近完整交易日或未通过健康门槛，不能据此下单。新的合格快照发布后自动恢复；已有持仓与订单不受影响。` : `The current snapshot (market date ${market ?? "—"}) is not aligned with the latest complete session or failed the health gate, so it cannot be traded. Ordering resumes automatically after the next eligible snapshot; existing positions and orders are unaffected.`}</p>
    <TmLinkButton href={picksHref} variant="secondary" size="sm">{zh ? "查看快照状态" : "View snapshot status"}</TmLinkButton>
  </div>;
}
