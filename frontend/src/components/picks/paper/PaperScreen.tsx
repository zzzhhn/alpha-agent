"use client";

/**
 * PaperScreen — client orchestrator for /paper. Owns the 4-tab state (synced
 * to the ?tab= URL query via router.replace, no Suspense boundary needed —
 * that's only required for useSearchParams, and the initial tab is read
 * server-side by page.tsx and passed in as a prop instead), and the
 * Promise.all concurrent data load PaperTab used to do (kept: principle 8,
 * "尊重时间"). All 4 panes share this one load rather than re-fetching per
 * tab switch.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CircleHelp } from "lucide-react";
import "driver.js/dist/driver.css";
import "./paper-tour-theme.css";
import {
  fetchPaperAccount,
  fetchOrders,
  fetchEquityCurve,
  fetchAttribution,
  cancelOrder,
  type AccountResponse,
  type OrderOut,
  type EquityCurveResponse,
  type TickerAttribution,
} from "@/lib/api/paper";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { TmChip } from "@/components/tm/TmSubbar";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { startPaperTour, hasSeenPaperTour } from "@/lib/paperTour";
import PaperOverviewPane from "./PaperOverviewPane";
import PaperTradePane from "./PaperTradePane";
import PaperCurvePane from "./PaperCurvePane";
import PaperOrdersPane from "./PaperOrdersPane";

import type { PaperTabKey } from "./tabs";
export type { PaperTabKey } from "./tabs";
import { PAPER_TABS } from "./tabs";  // shared with the server page — see tabs.ts

const TAB_LABEL_KEY: Record<PaperTabKey, Parameters<typeof t>[1]> = {
  overview: "sim.tabs.overview",
  trade: "sim.tabs.trade",
  curve: "sim.tabs.curve",
  orders: "sim.tabs.orders",
};

// Stable hooks for the onboarding tour (docs/superpowers/specs/
// 2026-07-26-paper-trading-v2-design.md "Onboarding") — targeted by
// data-tour rather than class names so a future style pass can't
// silently break the tour's element selectors.
const TAB_TOUR_KEY: Record<PaperTabKey, string> = {
  overview: "paper-tab-overview",
  trade: "paper-tab-trade",
  curve: "paper-tab-curve",
  orders: "paper-tab-orders",
};

export default function PaperScreen({ initialTab }: { readonly initialTab: PaperTabKey }) {
  const { locale } = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const [tab, setTab] = useState<PaperTabKey>(initialTab);

  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [orders, setOrders] = useState<readonly OrderOut[]>([]);
  const [curve, setCurve] = useState<EquityCurveResponse | null>(null);
  const [attribution, setAttribution] = useState<readonly TickerAttribution[]>([]);
  const [attributionStatus, setAttributionStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    await Promise.all([
      fetchPaperAccount().then(setAccount).catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      }),
      fetchOrders({ limit: 100 }).then((r) => setOrders(r.orders)).catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      }),
      fetchEquityCurve().then(setCurve).catch(() => null),
      fetchAttribution()
        .then((r) => {
          setAttribution(r.tickers);
          setAttributionStatus("ready");
        })
        .catch(() => setAttributionStatus("unavailable")),
    ]);
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  function changeTab(next: PaperTabKey) {
    setTab(next);
    router.replace(`${pathname}?tab=${next}`, { scroll: false });
  }

  // Auto-start the onboarding tour on first visit, once loading settles
  // and the tabbed panes are actually in the DOM. The ref guards against
  // React strict-mode's double effect invocation firing it twice.
  const tourAutoStarted = useRef(false);
  useEffect(() => {
    if (loading || tourAutoStarted.current || hasSeenPaperTour()) return;
    tourAutoStarted.current = true;
    const timer = setTimeout(() => startPaperTour(locale, changeTab), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  async function handleCancel(orderId: number) {
    await cancelOrder(orderId);
    await loadAll();
  }

  return (
    <TmScreen>
      <TmPane
        title={t(locale, "sim.page_title")}
        meta={
          <span className="flex items-center gap-2">
            <span>T+1</span>
            <button
              type="button"
              onClick={() => startPaperTour(locale, changeTab)}
              aria-label={t(locale, "sim.tour.help_btn")}
              title={t(locale, "sim.tour.help_btn")}
              className="text-tm-muted hover:text-tm-fg"
            >
              <CircleHelp className="h-3.5 w-3.5" strokeWidth={1.75} />
            </button>
          </span>
        }
      >
        <div role="tablist" aria-label="Paper trading tabs" className="flex flex-wrap items-center gap-1.5 px-3 py-2">
          {PAPER_TABS.map((k) => (
            <TmChip
              key={k}
              data-tour={TAB_TOUR_KEY[k]}
              on={tab === k}
              type="button"
              role="tab"
              aria-selected={tab === k}
              onClick={() => changeTab(k)}
            >
              {t(locale, TAB_LABEL_KEY[k])}
            </TmChip>
          ))}
        </div>
      </TmPane>

      <TmPane>
        {loading ? (
          <div className="flex items-center justify-center py-12 font-tm-mono text-[12px] text-tm-muted">
            {t(locale, "common.loading")}
          </div>
        ) : error ? (
          <div className="px-4 py-4 font-tm-mono text-[12px] text-tm-neg">{error}</div>
        ) : (
          <>
            {tab === "overview" && account ? (
              <PaperOverviewPane account={account} onReset={loadAll} onGoToTrade={() => changeTab("trade")} />
            ) : null}
            {tab === "trade" ? <PaperTradePane onPlaced={loadAll} /> : null}
            {tab === "curve" ? <PaperCurvePane curve={curve} /> : null}
            {tab === "orders" ? (
              <PaperOrdersPane
                orders={orders}
                onCancel={handleCancel}
                attribution={attribution}
                attributionStatus={attributionStatus}
              />
            ) : null}
          </>
        )}
      </TmPane>
    </TmScreen>
  );
}
