"use client";

import Link from "next/link";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  fetchPicks,
  type RatingCard,
  type RecommendationRunState,
} from "@/lib/api/picks";
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
import { isPicksSnapshotStale } from "@/lib/picks-freshness";
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
  const kind = searchParams.get("account") === "bot" ? "bot" : "human";
  const accountTabs = <SegmentedTabs<"human" | "bot"> className="paper-account-tabs shrink-0" active={kind} ariaLabel={t(locale, "sim.accounts.label")} items={[{key:"human",label:t(locale,"sim.accounts.human")},{key:"bot",label:t(locale,"sim.accounts.bot")}]} onChange={next => {
    const query = new URLSearchParams(searchParams.toString());
    query.set("account", next);
    if (next === "bot") query.delete("ticker");
    router.replace(`${pathname}?${query}`, { scroll: false });
  }} />;
  return kind === "bot" ? <PaperBotScreen accountTabs={accountTabs} /> : <HumanPaperScreen accountTabs={accountTabs} />;
}

function HumanPaperScreen({ accountTabs }: { readonly accountTabs: ReactNode }) {
  const { locale } = useLocale();
  const searchParams = useSearchParams();
  const requestedTicker = searchParams.get("ticker")?.trim().toUpperCase() ?? null;
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [orders, setOrders] = useState<readonly OrderOut[]>([]);
  const [curve, setCurve] = useState<EquityCurveResponse | null>(null);
  const [attribution, setAttribution] = useState<readonly TickerAttribution[]>([]);
  const [l2Summary, setL2Summary] = useState<L2Summary | null>(null);
  const [picks, setPicks] = useState<readonly RatingCard[]>([]);
  const [picksAsOf, setPicksAsOf] = useState<string | null>(null);
  const [picksServerStale, setPicksServerStale] = useState(false);
  const [picksTradable, setPicksTradable] = useState(false);
  const [picksRun, setPicksRun] = useState<RecommendationRunState | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string | null | undefined>(undefined);
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

  const loadAll = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setRefreshing(true);
    setPaperError(null);
    const [picksResult, accountResult, ordersResult, curveResult, attributionResult, l2Result] = await Promise.allSettled([
      fetchPicks(5),
      fetchPaperAccount(),
      fetchOrders({ limit: 20 }),
      fetchEquityCurve(),
      fetchAttribution(),
      fetchL2Summary(),
    ]);

    const nextErrors: typeof resourceErrors = {};
    const reason = (value: unknown) => value instanceof Error ? value.message : String(value);

    if (picksResult.status === "fulfilled") {
      setPicks(picksResult.value.picks);
      setPicksAsOf(picksResult.value.as_of);
      setPicksServerStale(picksResult.value.stale);
      setPicksTradable(picksResult.value.tradable);
      setPicksRun(picksResult.value.run);
    } else nextErrors.picks = reason(picksResult.reason);
    if (accountResult.status === "fulfilled") {
      setAccount(accountResult.value);
      setAuthRequired(false);
    } else if (accountResult.reason instanceof PaperApiError && accountResult.reason.status === 401) {
      setAuthRequired(true);
      setAccount(null);
    } else {
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
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const picksFrozen =
    picks.length > 0 &&
    (!picksTradable || isPicksSnapshotStale(picksAsOf, picksServerStale));

  useEffect(() => {
    if (picks.length === 0) return;
    if (picksFrozen) {
      setSelectedTicker(null);
      return;
    }
    if (selectedTicker === undefined) {
      setSelectedTicker(
        requestedTicker ? picks.find(pick => pick.ticker === requestedTicker)?.ticker ?? null : picks[0].ticker,
      );
    } else if (selectedTicker && !picks.some(pick => pick.ticker === selectedTicker)) setSelectedTicker(null);
  }, [picks, picksFrozen, requestedTicker, selectedTicker]);

  const selectedPick = useMemo(
    () => picks.find((pick) => pick.ticker === selectedTicker) ?? null,
    [picks, selectedTicker],
  );
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
          { label: locale === "zh" ? "推荐来源" : "Pick source", value: picksRun ? `RUN #${picksRun.run_id}` : "—", tone: picksFrozen ? "warning" : picksRun ? "positive" : "default" },
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

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane
          className="min-w-0 lg:border-r lg:border-tm-rule"
          title={zh ? "今日推荐 · 选择标的" : "Today's picks · Select a ticker"}
          meta={
            <span className="flex flex-wrap items-center gap-3"><span>{picksRun ? `${picksRun.market_date} · RUN #${picksRun.run_id}` : "—"}</span><TmLinkButton href="/picks">{zh ? "全部推荐" : "All picks"}</TmLinkButton></span>
          }
        >
          {resourceErrors.picks ? <SectionError detail={resourceErrors.picks} onRetry={() => void loadAll(false)} /> : null}
          {picksFrozen ? <FrozenRecommendations /> : null}
          {loading && picks.length === 0 ? <Loading /> : <PaperRecommendations picks={picks} selectedTicker={selectedTicker ?? null} actionable={!picksFrozen && !refreshing && !resourceErrors.picks} onSelect={(pick) => setSelectedTicker(pick.ticker)} />}
        </TmPane>
        <TmPane className="min-w-0" title={t(locale, "sim.workspace.order_title")} meta={selectedPick ? <TmButton variant="ghost" onClick={() => setSelectedTicker(null)}>{t(locale, "sim.workspace.clear")}</TmButton> : undefined}>
          <div ref={orderTicket} tabIndex={-1} aria-label={zh ? "模拟下单区" : "Paper order ticket"} className="px-4 py-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-tm-accent">
            {loading ? <Loading /> : picksFrozen ? <FrozenRecommendations /> : authRequired ? <AuthPrompt hint={t(locale, "sim.workspace.order_auth")} cta={t(locale, "sim.auth.cta")} /> : paperError ? <PaperError detail={paperError} /> : selectedPick && account ? (
              <SimOrderForm
                key={selectedPick.ticker}
                layout="ticket"
                disabled={refreshing || !!resourceErrors.picks}
                fixedTicker={selectedPick.ticker}
                locale={locale}
                onPlaced={() => { void loadAll(false); }}
                pickDate={selectedPick.market_date ?? picksRun?.market_date}
                pickTicker={selectedPick.ticker}
                pickRunId={selectedPick.run_id ?? picksRun?.run_id}
                latestPrice={selectedPick.latest_price}
                priceDate={selectedPick.price_date}
                availableCash={account.available_cash}
                portfolioValue={account.portfolio_value ?? undefined}
                targetWeight={0.02}
                initialSide={selectedPick.rating === "SELL" || selectedPick.rating === "UW" ? "sell" : "buy"}
              />
            ) : <p className="py-6 text-sm leading-6 text-tm-muted">{requestedTicker && !picks.some(p => p.ticker === requestedTicker) ? (zh ? `${requestedTicker} 不在当前推荐列表中，请从左侧重新选择。` : `${requestedTicker} is not in this shortlist. Choose a ticker on the left.`) : (zh ? "从左侧选择一个标的，核对数量后再提交模拟单。" : "Choose a ticker on the left, then review the quantity before submitting.")}</p>}
          </div>
        </TmPane>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane className="min-w-0 lg:border-r lg:border-tm-rule" title={t(locale, "sim.workspace.positions")} meta={accountUnavailable ? "—" : `${account.positions.length} ${zh ? "个标的" : "positions"}`}>
          {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} /> : resourceErrors.account ? <SectionError detail={resourceErrors.account} onRetry={() => void loadAll(false)} /> : account ? <>
            {resourceErrors.attribution ? <SectionError detail={resourceErrors.attribution} onRetry={() => void loadAll(false)} /> : null}
            <PaperPositionsWithSource positions={account.positions} attribution={attribution} attributionAvailable={!resourceErrors.attribution} pendingOrders={account.pending_orders} onChoose={showOrderTicket} />
          </> : null}
        </TmPane>
        <TmPane className="min-w-0" title={zh ? "我的模拟净值" : "My paper equity"} meta={curve?.base_date ?? (zh ? "按日估值" : "Daily marks")}>
          {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} /> : resourceErrors.curve ? <SectionError detail={resourceErrors.curve} onRetry={() => void loadAll(false)} /> : <PaperCurvePane curve={curve} compact showDisclaimer={false} />}
          {!loading && !authRequired ? <><TmDisclosureButton expanded={sourceOpen} onClick={() => setSourceOpen(v => !v)} aria-controls="paper-source-details" label={t(locale, "sim.workspace.source_record")} />{sourceOpen ? <div id="paper-source-details">{resourceErrors.attribution ? <SectionError detail={resourceErrors.attribution} onRetry={() => void loadAll(false)} /> : <PaperSourceSummary rows={attribution} />}</div> : null}</> : null}
        </TmPane>
      </div>

      <TmPane title={t(locale, "sim.workspace.recent_orders")} meta={zh ? "最近 20 笔 · 市价单下一交易日收盘撮合" : "Latest 20 · Market orders fill at the next session's close"}>
        {loading ? <Loading /> : authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} /> : resourceErrors.orders ? <SectionError detail={resourceErrors.orders} onRetry={() => void loadAll(false)} /> : <PaperOrdersPane orders={orders} onCancel={handleCancel} attribution={attribution} attributionStatus={resourceErrors.attribution ? "unavailable" : "ready"} showAttribution={false} showDisclaimer={false} />}
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

function AuthPrompt({ hint, cta }: { readonly hint: string; readonly cta: string }) {
  return <div className="flex flex-col items-start gap-3 px-3 py-8"><p className="font-tm-mono text-xs text-tm-muted">{hint}</p><Link href="/signin?callbackUrl=/paper" className="border border-tm-accent px-3 py-1.5 font-tm-mono text-xs text-tm-accent hover:bg-tm-accent hover:text-tm-bg">{cta}</Link></div>;
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
  return <p className="mx-3 my-2 rounded-[2px] border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 font-tm-mono text-xs leading-5 text-tm-neg">{t(locale, "picks.stale_freeze_banner")}</p>;
}
