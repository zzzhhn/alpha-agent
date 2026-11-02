"use client";

// PaperOrdersPane — order history + per-ticker attribution rollup + the
// honest disclaimer (3rd of its 3 required placements).
import type { TickerAttribution, OrderOut } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useState } from "react";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmButton } from "@/components/tm/TmButton";
import { t, type Locale } from "@/lib/i18n";
import { StatusChip, Disclaimer, TwoStepConfirm } from "./PaperUi";
import PaperAttributionTable from "./PaperAttributionTable";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

const ORDER_HEADERS: Record<Locale, string[]> = {
  zh: ["日期", "代码", "方向", "类型", "数量", "限价", "成交价", "状态"],
  en: ["Date", "Ticker", "Side", "Type", "Qty", "Limit", "Fill", "Status"],
};

export default function PaperOrdersPane({
  orders,
  onCancel,
  attribution,
  attributionStatus,
  showAttribution = true,
  showDisclaimer = true,
  botMode = false,
  onInspectOrder,
}: {
  readonly orders: readonly OrderOut[];
  readonly onCancel: (orderId: number) => Promise<void>;
  readonly attribution: readonly TickerAttribution[];
  readonly attributionStatus: "loading" | "ready" | "unavailable";
  readonly showAttribution?: boolean;
  readonly showDisclaimer?: boolean;
  readonly botMode?: boolean;
  readonly onInspectOrder?: (order: OrderOut) => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [pageSize, setPageSize] = useState(5);
  const [paging, setPaging] = useState({ source: orders, page: 1 });
  const page = paging.source === orders ? Math.min(paging.page, Math.max(1, Math.ceil(orders.length / pageSize))) : 1;
  const visibleOrders = orders.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="flex flex-col gap-5 px-3 py-3">
      <TmTableFrame>
        {orders.length === 0 ? (
          <p className="py-2 text-sm text-tm-muted">{botMode ? t(locale, "sim.bot.orders_empty") : zh ? "尚无模拟订单。提交后的订单会在这里显示待成交、成交或失败原因。" : "No paper orders yet. Submitted orders will show their execution status or failure reason here."}</p>
        ) : (
          <TmTable density="compact" caption={t(locale, "sim.orders.title")} className="text-left">
            <TmTableHead>
              <TmTableRow>
                {ORDER_HEADERS[locale].map((h) => (
                  <TmTableHeaderCell key={h} className="text-xs tracking-wide">
                    {h}
                  </TmTableHeaderCell>
                ))}
                {botMode ? <TmTableHeaderCell>{t(locale, "sim.bot.fee")}</TmTableHeaderCell> : null}
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {visibleOrders.map((o) => (
                <OrderRow key={o.id} order={o} locale={locale} onCancel={onCancel} botMode={botMode} onInspectOrder={onInspectOrder} />
              ))}
            </TmTableBody>
          </TmTable>
        )}
      </TmTableFrame>
      {orders.length > 5 ? <TmPagination page={page} pageSize={pageSize} totalItems={orders.length} pageSizeOptions={[5, 10, 20]} onPageChange={next => setPaging({ source: orders, page: next })} onPageSizeChange={next => {setPageSize(next);setPaging({ source: orders, page: 1 });}} labels={{navigation:zh ? "订单分页" : "Order pagination",previous:zh ? "上一页" : "Previous",previousAriaLabel:zh ? "上一页订单" : "Previous orders",next:zh ? "下一页" : "Next",nextAriaLabel:zh ? "下一页订单" : "Next orders",page:(current,count) => `${current} / ${count}`,pageSize:zh ? "每页" : "Per page",total:total => zh ? `本次已载入 ${total} 笔订单` : `${total} loaded orders`}} /> : null}

      {showAttribution ? <div>
        <div className="mb-2 border-b border-tm-rule pb-1.5 font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-muted">
          {t(locale, "sim.attribution.title")}
        </div>
        <PaperAttributionTable rows={attribution} status={attributionStatus} />
      </div> : null}

      {showDisclaimer ? <Disclaimer /> : null}
    </div>
  );
}

function OrderRow({
  order: o,
  locale,
  onCancel,
  botMode,
  onInspectOrder,
}: {
  readonly order: OrderOut;
  readonly locale: Locale;
  readonly onCancel: (orderId: number) => Promise<void>;
  readonly botMode: boolean;
  readonly onInspectOrder?: (order: OrderOut) => void;
}) {
  const statusLabel =
    o.status === "failed"
      ? t(locale, "sim.status.failed")
      : ["accepted", "pending_market_data", "expired", "rejected", "cancel_requested"].includes(o.status)
        ? t(locale, `sim.bot.order.${o.status}` as "sim.bot.order.accepted")
        : ["pending", "filled", "cancelled"].includes(o.status) ? t(locale, `sim.status.${o.status}` as "sim.status.pending") : (locale === "zh" ? "状态待确认" : "Status unavailable");
  return (
    <TmTableRow>
      <TmTableCell className="text-xs text-tm-muted">{o.signal_date}</TmTableCell>
      <TmTableRowHeader className="text-[12px] font-semibold text-tm-accent">
        {o.ticker}
        {o.pick_ticker ? (
          <span
            title={t(locale, "sim.followed_tag")}
            className="ml-1.5 border border-tm-rule px-1 py-px align-middle font-tm-mono text-xs uppercase text-tm-muted"
          >
            {t(locale, "sim.followed_tag")}
          </span>
        ) : null}
      </TmTableRowHeader>
      <TmTableCell className={`text-xs ${o.side === "buy" ? "text-tm-pos" : "text-tm-neg"}`}>
        {t(locale, `sim.order_side.${o.side}` as "sim.order_side.buy")}
      </TmTableCell>
      <TmTableCell className="text-xs text-tm-fg-2">
        {t(locale, `sim.order_type.${o.order_type}` as "sim.order_type.market")}
      </TmTableCell>
      <TmTableCell numeric className="text-xs text-tm-fg-2">{o.qty}</TmTableCell>
      <TmTableCell numeric className="text-xs text-tm-fg-2">
        {o.limit_price !== null ? `$${o.limit_price.toFixed(2)}` : "—"}
      </TmTableCell>
      <TmTableCell numeric className="text-xs text-tm-fg-2">
        {o.fill_price !== null ? `$${o.fill_price.toFixed(2)}` : "—"}
      </TmTableCell>
      <TmTableCell className="text-xs">
        <div className="flex items-center gap-2">
          <StatusChip status={o.status} label={statusLabel} />
          {o.status === "failed" && o.fail_reason ? (
            <span className="font-tm-mono text-xs text-tm-muted" title={o.fail_reason}>
              {o.fail_reason}
            </span>
          ) : null}
          {!botMode && o.status === "pending" ? (
            <TwoStepConfirm
              idleLabel={t(locale, "sim.cancel_btn")}
              warnText={t(locale, "sim.cancel_btn") + "?"}
              doneText={t(locale, "sim.status.cancelled")}
              onConfirm={() => onCancel(o.id)}
            />
          ) : null}
        </div>
      </TmTableCell>
      {botMode ? <TmTableCell numeric>{o.transaction_cost == null ? t(locale, "sim.bot.fee_unknown") : `$${o.transaction_cost.toFixed(2)}`}{onInspectOrder ? <TmButton variant="ghost" size="xs" className="ml-2" onClick={()=>onInspectOrder(o)} aria-label={`${t(locale,"sim.bot.details")} ${o.ticker} #${o.id}`}>{t(locale,"sim.bot.details")}</TmButton> : null}</TmTableCell> : null}
    </TmTableRow>
  );
}
