// frontend/src/components/picks/PaperTab.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchPaperAccount,
  fetchOrders,
  fetchEquityCurve,
  resetAccount,
  cancelOrder,
  type AccountResponse,
  type OrderOut,
  type EquityCurveResponse,
} from "@/lib/api/paper";
import { SegmentedTabs, type SegmentedTabItem } from "@/components/ui/SegmentedTabs";
import SimPositionRow from "./SimPositionRow";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import clsx from "clsx";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

type SubTab = "overview" | "curve" | "orders";

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const PCT = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

export default function PaperTab({ onPositionsChange }: {
  readonly onPositionsChange?: (positions: ReadonlyMap<string, number>) => void;
}) {
  const { locale } = useLocale();
  const [tab, setTab] = useState<SubTab>("overview");
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [orders, setOrders] = useState<readonly OrderOut[]>([]);
  const [curve, setCurve] = useState<EquityCurveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  const loadAccount = useCallback(async () => {
    try {
      const acct = await fetchPaperAccount();
      setAccount(acct);
      // Propagate held positions up to PicksBrowser for the sim buttons
      const map = new Map<string, number>(
        acct.positions.map((p) => [p.ticker, p.qty])
      );
      onPositionsChange?.(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [onPositionsChange]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    await Promise.all([
      loadAccount(),
      fetchOrders({ limit: 100 }).then((r) => setOrders(r.orders)).catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      }),
      fetchEquityCurve().then(setCurve).catch(() => null),
    ]);
    setLoading(false);
  }, [loadAccount]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  async function handleReset() {
    if (!window.confirm(t(locale, "sim.reset_confirm"))) return;
    setResetting(true);
    try {
      await resetAccount();
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResetting(false);
    }
  }

  async function handleCancel(orderId: number) {
    try {
      await cancelOrder(orderId);
      await loadAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const subTabs: ReadonlyArray<SegmentedTabItem<SubTab>> = [
    { key: "overview", label: t(locale, "sim.account.tab") },
    { key: "curve", label: t(locale, "sim.equity_curve.title") },
    { key: "orders", label: t(locale, "sim.orders.title") },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 font-tm-mono text-[12px] text-tm-muted">
        {t(locale, "common.loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-4 font-tm-mono text-[12px] text-tm-neg">{error}</div>
    );
  }

  return (
    <div className="flex flex-col">
      <SegmentedTabs items={subTabs} active={tab} onChange={setTab} ariaLabel="Paper trading sub-tabs" />

      {tab === "overview" && account && (
        <div className="flex flex-col gap-4 px-4 py-4">
          {/* KPI strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: t(locale, "sim.account.nav"), value: `$${FMT.format(account.portfolio_value)}`, sub: PCT(account.total_return_pct), subPos: account.total_return_pct >= 0 },
              { label: t(locale, "sim.account.cash"), value: `$${FMT.format(account.cash)}`, sub: null, subPos: true },
              { label: t(locale, "sim.account.unrealized"), value: `${account.unrealized_pnl >= 0 ? "+" : ""}$${FMT.format(Math.abs(account.unrealized_pnl))}`, sub: null, subPos: account.unrealized_pnl >= 0 },
              { label: t(locale, "sim.account.realized"), value: `${account.realized_pnl >= 0 ? "+" : ""}$${FMT.format(Math.abs(account.realized_pnl))}`, sub: null, subPos: account.realized_pnl >= 0 },
            ].map((kpi) => (
              <div key={kpi.label} className="rounded border border-tm-rule bg-tm-bg-2 px-3 py-2.5">
                <div className="font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">{kpi.label}</div>
                <div className={clsx("mt-1 font-tm-mono text-[14px] font-semibold tabular-nums", kpi.subPos ? "text-tm-pos" : "text-tm-neg")}>
                  {kpi.value}
                </div>
                {kpi.sub && <div className="font-tm-mono text-[10px] text-tm-muted">{kpi.sub}</div>}
              </div>
            ))}
          </div>

          {/* Positions table */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="font-tm-mono text-[11px] uppercase tracking-wide text-tm-muted">
                {t(locale, "sim.positions.title")}
              </span>
              <button
                type="button"
                onClick={() => { void handleReset(); }}
                disabled={resetting}
                className="rounded border border-tm-rule px-2 py-0.5 font-tm-mono text-[10px] text-tm-muted hover:border-tm-neg hover:text-tm-neg transition-colors disabled:opacity-50"
              >
                {resetting ? "..." : t(locale, "sim.reset_btn")}
              </button>
            </div>
            {account.positions.length === 0 ? (
              <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.noData")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-tm-rule">
                      {[locale === "zh" ? "代码" : "Ticker",
                        locale === "zh" ? "数量" : "Qty",
                        locale === "zh" ? "均价" : "Avg Cost",
                        locale === "zh" ? "现价" : "Price",
                        locale === "zh" ? "盈亏" : "PnL",
                        locale === "zh" ? "盈亏%" : "PnL%",
                      ].map((h) => (
                        <th key={h} className="px-3 py-1.5 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted text-right first:text-left">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {account.positions.map((p) => (
                      <SimPositionRow key={p.ticker} pos={p} locale={locale} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Disclaimer */}
          <p className="font-tm-mono text-[10px] text-tm-muted">
            ⚠ {t(locale, "sim.disclaimer")}
          </p>
        </div>
      )}

      {tab === "curve" && (
        <div className="px-4 py-4">
          {!curve || curve.series.length === 0 ? (
            <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.noData")}</p>
          ) : (
            <div style={{ width: "100%", height: 300 }}>
              <ResponsiveContainer>
                <ComposedChart data={curve.series as unknown as Record<string, unknown>[]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-tm-rule)" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fontFamily: "var(--font-tm-mono)" }} />
                  <YAxis tick={{ fontSize: 10, fontFamily: "var(--font-tm-mono)" }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Line
                    type="monotone"
                    dataKey="portfolio_value"
                    stroke="var(--color-tm-accent)"
                    dot={false}
                    name={t(locale, "sim.account.nav")}
                  />
                  <Line
                    type="monotone"
                    dataKey="benchmark_index"
                    stroke="var(--color-tm-muted)"
                    strokeDasharray="4 2"
                    dot={false}
                    name="SPY"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-2 font-tm-mono text-[10px] text-tm-muted">
            ⚠ {t(locale, "sim.disclaimer")}
          </p>
        </div>
      )}

      {tab === "orders" && (
        <div className="overflow-x-auto px-4 py-4">
          {orders.length === 0 ? (
            <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.noData")}</p>
          ) : (
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-tm-rule">
                  {(locale === "zh"
                    ? ["日期", "代码", "方向", "类型", "数量", "限价", "成交价", "状态"]
                    : ["Date", "Ticker", "Side", "Type", "Qty", "Limit", "Fill", "Status"]
                  ).map((h) => (
                    <th key={h} className="px-3 py-1.5 font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-b border-tm-rule hover:bg-tm-bg-2">
                    <td className="px-3 py-2 font-tm-mono text-[11px] text-tm-muted">{o.signal_date}</td>
                    <td className="px-3 py-2 font-tm-mono text-[12px] font-semibold text-tm-accent">{o.ticker}</td>
                    <td className={clsx("px-3 py-2 font-tm-mono text-[11px]", o.side === "buy" ? "text-tm-pos" : "text-tm-neg")}>
                      {t(locale, `sim.order_side.${o.side}` as "sim.order_side.buy")}
                    </td>
                    <td className="px-3 py-2 font-tm-mono text-[11px] text-tm-fg-2">
                      {t(locale, `sim.order_type.${o.order_type}` as "sim.order_type.market")}
                    </td>
                    <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2">{o.qty}</td>
                    <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2">
                      {o.limit_price !== null ? `$${o.limit_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-3 py-2 font-tm-mono text-[11px] tabular-nums text-tm-fg-2">
                      {o.fill_price !== null ? `$${o.fill_price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-3 py-2 font-tm-mono text-[11px]">
                      <span className={clsx(
                        "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        o.status === "filled" ? "bg-tm-pos/10 text-tm-pos"
                          : o.status === "pending" ? "bg-tm-warn/10 text-tm-warn"
                            : "bg-tm-muted/10 text-tm-muted",
                      )}>
                        {t(locale, `sim.status.${o.status}` as "sim.status.pending")}
                      </span>
                      {o.status === "pending" && (
                        <button
                          type="button"
                          onClick={() => { void handleCancel(o.id); }}
                          className="ml-2 font-tm-mono text-[10px] text-tm-muted hover:text-tm-neg"
                        >
                          {locale === "zh" ? "撤销" : "Cancel"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
