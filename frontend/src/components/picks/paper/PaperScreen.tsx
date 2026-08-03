"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleHelp, X } from "lucide-react";
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
import { TmButton } from "@/components/tm/TmButton";
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

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export default function PaperScreen() {
  const { locale } = useLocale();
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
  const [now, setNow] = useState(() => Date.now());
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);
  const [paperError, setPaperError] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);

  const loadAll = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setPaperError(null);
    const [picksResult, accountResult, ordersResult, curveResult, attributionResult, l2Result] = await Promise.allSettled([
      fetchPicks(5),
      fetchPaperAccount(),
      fetchOrders({ limit: 20 }),
      fetchEquityCurve(),
      fetchAttribution(),
      fetchL2Summary(),
    ]);

    if (picksResult.status === "fulfilled") {
      setPicks(picksResult.value.picks);
      setPicksAsOf(picksResult.value.as_of);
      setPicksServerStale(picksResult.value.stale);
      setPicksTradable(picksResult.value.tradable);
      setPicksRun(picksResult.value.run);
    }
    if (accountResult.status === "fulfilled") {
      setAccount(accountResult.value);
      setAuthRequired(false);
    } else if (accountResult.reason instanceof PaperApiError && accountResult.reason.status === 401) {
      setAuthRequired(true);
      setAccount(null);
    } else {
      setPaperError(accountResult.reason instanceof Error ? accountResult.reason.message : String(accountResult.reason));
    }
    if (ordersResult.status === "fulfilled") setOrders(ordersResult.value.orders);
    if (curveResult.status === "fulfilled") setCurve(curveResult.value);
    if (attributionResult.status === "fulfilled") setAttribution(attributionResult.value.tickers);
    if (l2Result.status === "fulfilled") setL2Summary(l2Result.value);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  const picksFrozen =
    picks.length > 0 &&
    (!picksTradable || isPicksSnapshotStale(picksAsOf, picksServerStale, now));

  useEffect(() => {
    if (picks.length === 0) {
      setSelectedTicker(null);
      return;
    }
    if (picksFrozen) {
      setSelectedTicker(null);
      return;
    }
    if (!selectedTicker || !picks.some((pick) => pick.ticker === selectedTicker)) {
      setSelectedTicker(picks[0].ticker);
    }
  }, [picks, picksFrozen, selectedTicker]);

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

  const totalReturn = account?.total_return_pct ?? 0;

  return (
    <TmScreen className="overflow-y-auto">
      <TmPane
        title={t(locale, "sim.page_title")}
        meta={
          <span className="flex items-center gap-2">
            <span>{t(locale, "sim.workspace.disclosure")}</span>
            <button
              type="button"
              aria-label={t(locale, "sim.workspace.guide_title")}
              className="text-tm-muted hover:text-tm-fg"
              onClick={() => setGuideOpen((open) => !open)}
            >
              <CircleHelp className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          </span>
        }
      >
        <div className="grid grid-cols-1 gap-3 px-3 py-2.5 sm:grid-cols-[minmax(14rem,1fr)_minmax(0,2fr)_auto] sm:items-center">
          <div className="min-w-0">
            <div className="font-tm-mono text-[12px] text-tm-fg">{t(locale, "sim.workspace.subtitle")}</div>
            <div className="mt-1 flex items-center gap-2 font-tm-mono text-[9.5px] uppercase tracking-wide text-tm-muted">
              <span>01 {t(locale, "sim.workspace.guide_step1")}</span><span>→</span>
              <span>02 {t(locale, "sim.workspace.guide_step2")}</span><span>→</span>
              <span>03 {t(locale, "sim.workspace.guide_step3")}</span>
            </div>
          </div>
          <div className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
            <Metric label={t(locale, "sim.account.nav")} value={account ? `$${FMT.format(account.portfolio_value)}` : "—"} tone={totalReturn >= 0 ? "text-tm-pos" : "text-tm-neg"} />
            <Metric label={t(locale, "sim.account.cash")} value={account ? `$${FMT.format(account.cash)}` : "—"} />
            <Metric label={t(locale, "sim.account.unrealized")} value={account ? `${account.unrealized_pnl >= 0 ? "+" : "-"}$${FMT.format(Math.abs(account.unrealized_pnl))}` : "—"} tone={(account?.unrealized_pnl ?? 0) >= 0 ? "text-tm-pos" : "text-tm-neg"} />
            <Metric label={t(locale, "sim.workspace.total_return")} value={account ? `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%` : "—"} tone={totalReturn >= 0 ? "text-tm-pos" : "text-tm-neg"} />
          </div>
          {account ? <div className="justify-self-start sm:justify-self-end"><TwoStepConfirm idleLabel={t(locale, "sim.reset_btn")} warnText={t(locale, "sim.reset_confirm")} doneText={t(locale, "sim.reset_done")} onConfirm={handleReset} /></div> : null}
        </div>
        {guideOpen ? (
          <div className="relative border-t border-tm-rule bg-tm-bg-2 px-3 py-2 pr-10 font-tm-mono text-[10px] leading-5 text-tm-muted">
            {t(locale, "sim.tour.step2_desc")} {t(locale, "sim.workspace.source_note")}
            <button type="button" aria-label={t(locale, "sim.close")} className="absolute right-3 top-2 text-tm-muted hover:text-tm-fg" onClick={() => setGuideOpen(false)}><X className="h-3.5 w-3.5" /></button>
          </div>
        ) : null}
      </TmPane>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane
          standalone
          title={t(locale, "sim.workspace.today_picks")}
          meta={
            picksRun
              ? `${picksRun.market_date} · RUN #${picksRun.run_id}`
              : picks[0]?.price_date ?? "—"
          }
        >
          {picksFrozen ? <FrozenRecommendations /> : null}
          {loading && picks.length === 0 ? <Loading /> : <PaperRecommendations picks={picks} selectedTicker={selectedTicker} actionable={!picksFrozen} onSelect={(pick) => setSelectedTicker(pick.ticker)} />}
        </TmPane>
        <TmPane standalone title={selectedPick ? `${t(locale, "sim.workspace.order_title")} · ${selectedPick.ticker}` : t(locale, "sim.workspace.order_title")} meta={selectedPick ? <TmButton variant="ghost" onClick={() => setSelectedTicker(null)}>{t(locale, "sim.workspace.clear")}</TmButton> : undefined}>
          <div className="px-3 py-3">
            {picksFrozen ? <FrozenRecommendations /> : authRequired ? <AuthPrompt hint={t(locale, "sim.workspace.order_auth")} cta={t(locale, "sim.auth.cta")} /> : selectedPick && account ? (
              <SimOrderForm
                key={selectedPick.ticker}
                fixedTicker={selectedPick.ticker}
                locale={locale}
                onPlaced={() => { void loadAll(false); }}
                pickDate={selectedPick.market_date ?? picksRun?.market_date}
                pickTicker={selectedPick.ticker}
                pickRunId={selectedPick.run_id ?? picksRun?.run_id}
                latestPrice={selectedPick.latest_price}
                priceDate={selectedPick.price_date}
                availableCash={account.available_cash}
                initialSide={selectedPick.rating === "SELL" || selectedPick.rating === "UW" ? "sell" : "buy"}
              />
            ) : paperError ? <PaperError detail={paperError} /> : <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "sim.workspace.no_picks")}</p>}
          </div>
        </TmPane>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.65fr)_minmax(330px,0.85fr)]">
        <TmPane standalone title={t(locale, "sim.workspace.positions")}>
          {authRequired ? <AuthPrompt hint={t(locale, "sim.auth.hint")} cta={t(locale, "sim.auth.cta")} /> : <PaperPositionsWithSource positions={account?.positions ?? []} attribution={attribution} />}
        </TmPane>
        <TmPane standalone title={t(locale, "sim.workspace.performance")}>
          <PaperCurvePane curve={curve} compact showDisclaimer={false} />
          <PaperSourceSummary rows={attribution} />
          <PaperL2Evidence summary={l2Summary} />
        </TmPane>
      </div>

      <TmPane title={t(locale, "sim.workspace.recent_orders")} meta={t(locale, "sim.workspace.disclosure")}>
        <PaperOrdersPane orders={orders} onCancel={handleCancel} attribution={attribution} attributionStatus="ready" showAttribution={false} />
      </TmPane>
    </TmScreen>
  );
}

function Loading() {
  const { locale } = useLocale();
  return <div className="px-3 py-10 font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.loading")}</div>;
}

function AuthPrompt({ hint, cta }: { readonly hint: string; readonly cta: string }) {
  return <div className="flex flex-col items-start gap-3 px-3 py-8"><p className="font-tm-mono text-[11px] text-tm-muted">{hint}</p><Link href="/signin?callbackUrl=/paper" className="border border-tm-accent px-3 py-1.5 font-tm-mono text-[11px] text-tm-accent hover:bg-tm-accent hover:text-tm-bg">{cta}</Link></div>;
}

function PaperError({ detail }: { readonly detail: string }) {
  const { locale } = useLocale();
  return <p className="font-tm-mono text-[11px] leading-5 text-tm-neg">{t(locale, "sim.load_error_hint")} <span className="text-tm-muted">({detail})</span></p>;
}

function FrozenRecommendations() {
  const { locale } = useLocale();
  return <p className="mx-3 my-2 rounded border border-tm-neg/40 bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] leading-5 text-tm-neg">{t(locale, "picks.stale_freeze_banner")}</p>;
}
