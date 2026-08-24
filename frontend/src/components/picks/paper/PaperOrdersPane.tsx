"use client";

// PaperOrdersPane — order history + per-ticker attribution rollup + the
// honest disclaimer (3rd of its 3 required placements).
import type { TickerAttribution, OrderOut } from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
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
}: {
  readonly orders: readonly OrderOut[];
  readonly onCancel: (orderId: number) => Promise<void>;
  readonly attribution: readonly TickerAttribution[];
  readonly attributionStatus: "loading" | "ready" | "unavailable";
  readonly showAttribution?: boolean;
  readonly showDisclaimer?: boolean;
}) {
  const { locale } = useLocale();

  return (
    <div className="flex flex-col gap-5 px-3 py-3">
      <TmTableFrame>
        {orders.length === 0 ? (
          <p className="font-tm-mono text-[11px] text-tm-muted">{t(locale, "common.noData")}</p>
        ) : (
          <TmTable density="compact" caption={t(locale, "sim.orders.title")} className="text-left">
            <TmTableHead>
              <TmTableRow>
                {ORDER_HEADERS[locale].map((h) => (
                  <TmTableHeaderCell key={h} className="text-[10px] tracking-wide">
                    {h}
                  </TmTableHeaderCell>
                ))}
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {orders.map((o) => (
                <OrderRow key={o.id} order={o} locale={locale} onCancel={onCancel} />
              ))}
            </TmTableBody>
          </TmTable>
        )}
      </TmTableFrame>

      {showAttribution ? <div>
        <div className="mb-2 border-b border-tm-rule pb-1.5 font-tm-mono text-[10px] uppercase tracking-[0.08em] text-tm-muted">
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
}: {
  readonly order: OrderOut;
  readonly locale: Locale;
  readonly onCancel: (orderId: number) => Promise<void>;
}) {
  const statusLabel =
    o.status === "failed"
      ? t(locale, "sim.status.failed")
      : t(locale, `sim.status.${o.status}` as "sim.status.pending");
  return (
    <TmTableRow>
      <TmTableCell className="text-[11px] text-tm-muted">{o.signal_date}</TmTableCell>
      <TmTableRowHeader className="text-[12px] font-semibold text-tm-accent">
        {o.ticker}
        {o.pick_ticker ? (
          <span
            title={t(locale, "sim.followed_tag")}
            className="ml-1.5 border border-tm-rule px-1 py-px align-middle font-tm-mono text-[8px] uppercase text-tm-muted"
          >
            {t(locale, "sim.followed_tag")}
          </span>
        ) : null}
      </TmTableRowHeader>
      <TmTableCell className={`text-[11px] ${o.side === "buy" ? "text-tm-pos" : "text-tm-neg"}`}>
        {t(locale, `sim.order_side.${o.side}` as "sim.order_side.buy")}
      </TmTableCell>
      <TmTableCell className="text-[11px] text-tm-fg-2">
        {t(locale, `sim.order_type.${o.order_type}` as "sim.order_type.market")}
      </TmTableCell>
      <TmTableCell numeric className="text-[11px] text-tm-fg-2">{o.qty}</TmTableCell>
      <TmTableCell numeric className="text-[11px] text-tm-fg-2">
        {o.limit_price !== null ? `$${o.limit_price.toFixed(2)}` : "—"}
      </TmTableCell>
      <TmTableCell numeric className="text-[11px] text-tm-fg-2">
        {o.fill_price !== null ? `$${o.fill_price.toFixed(2)}` : "—"}
      </TmTableCell>
      <TmTableCell className="text-[11px]">
        <div className="flex items-center gap-2">
          <StatusChip status={o.status} label={statusLabel} />
          {o.status === "failed" && o.fail_reason ? (
            <span className="font-tm-mono text-[10px] text-tm-muted" title={o.fail_reason}>
              {o.fail_reason}
            </span>
          ) : null}
          {o.status === "pending" ? (
            <TwoStepConfirm
              idleLabel={t(locale, "sim.cancel_btn")}
              warnText={t(locale, "sim.cancel_btn") + "?"}
              doneText={t(locale, "sim.status.cancelled")}
              onConfirm={() => onCancel(o.id)}
            />
          ) : null}
        </div>
      </TmTableCell>
    </TmTableRow>
  );
}
