// frontend/src/components/picks/SimOrderForm.tsx
"use client";

/**
 * SimOrderForm — reusable, COMPACT order-ticket form (terminal density).
 * Layout: one horizontal controls row (side · type · qty · limit · ticker) that
 * wraps gracefully in the narrow row-drawer, then a footer row with buying
 * power + a single primary "下单" action. Matches the dense reference mockup —
 * no full-width giant buttons, one green primary, subtle segmented toggles.
 *
 * Used by:
 *  - SimOrderDrawer (fixedTicker set → ticker input hidden)
 *  - PaperTab 账户概况 view (ticker editable)
 */
import { useEffect, useState } from "react";
import { placeOrder, fetchPaperAccount } from "@/lib/api/paper";
import { t, type Locale } from "@/lib/i18n";
import { CheckCircle } from "lucide-react";
import clsx from "clsx";

interface Props {
  /** When provided the ticker input is hidden and this value is used. */
  readonly fixedTicker?: string;
  readonly locale: Locale;
  readonly onPlaced: () => void;
}

const FMT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

const FIELD_LABEL =
  "mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted";
const INPUT =
  "rounded border border-tm-rule bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-[13px] text-tm-fg focus:border-tm-accent focus:outline-none";

/** Compact segmented pills — auto width, subtle fill on the active option. */
function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: ReadonlyArray<{ key: T; label: string; active: string }>;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-tm-rule">
      {options.map((o, i) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          className={clsx(
            "px-3 py-1 font-tm-mono text-[11px] font-semibold uppercase transition-colors",
            i > 0 && "border-l border-tm-rule",
            value === o.key
              ? o.active
              : "text-tm-muted hover:bg-tm-bg-2 hover:text-tm-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function SimOrderForm({ fixedTicker, locale, onPlaced }: Props) {
  const [ticker, setTicker] = useState(fixedTicker ?? "");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [qty, setQty] = useState<string>("10");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [placed, setPlaced] = useState(false);
  const [cash, setCash] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPaperAccount()
      .then((a) => { if (!cancelled) setCash(a.cash); })
      .catch(() => { /* non-fatal — cash display remains blank */ });
    return () => { cancelled = true; };
  }, []);

  const qtyNum = parseInt(qty, 10);
  const limitNum = parseFloat(limitPrice);
  const estimatedCost =
    !isNaN(qtyNum) && orderType === "limit" && !isNaN(limitNum)
      ? qtyNum * limitNum
      : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPlaced(false);
    const effectiveTicker = (fixedTicker ?? ticker).trim().toUpperCase();
    if (!effectiveTicker) { setError(t(locale, "sim.form.ticker_required")); return; }
    if (isNaN(qtyNum) || qtyNum <= 0) { setError(t(locale, "sim.form.qty_error")); return; }
    if (orderType === "limit" && (isNaN(limitNum) || limitNum <= 0)) {
      setError(t(locale, "sim.form.limit_error")); return;
    }
    setSubmitting(true);
    try {
      await placeOrder({
        ticker: effectiveTicker, side, order_type: orderType, qty: qtyNum,
        ...(orderType === "limit" ? { limit_price: limitNum } : {}),
      });
      setPlaced(true);
      fetchPaperAccount().then((a) => setCash(a.cash)).catch(() => {});
      onPlaced();
      setTimeout(() => setPlaced(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {/* Controls row — packs horizontally, wraps in the narrow drawer */}
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        {!fixedTicker && (
          <div>
            <label className={FIELD_LABEL}>{t(locale, "sim.form.ticker_label")}</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="AAPL"
              className={clsx(INPUT, "w-28 uppercase placeholder:normal-case placeholder:text-tm-muted")}
            />
          </div>
        )}
        {fixedTicker && (
          <div className="self-center">
            <span className="font-tm-mono text-[15px] font-bold text-tm-fg">{fixedTicker}</span>
          </div>
        )}
        <div>
          <label className={FIELD_LABEL}>{t(locale, "sim.form.side_label")}</label>
          <Segmented
            value={side}
            onChange={setSide}
            options={[
              { key: "buy", label: t(locale, "sim.order_side.buy"), active: "bg-tm-pos text-tm-bg" },
              { key: "sell", label: t(locale, "sim.order_side.sell"), active: "bg-tm-neg text-tm-bg" },
            ]}
          />
        </div>
        <div>
          <label className={FIELD_LABEL}>{t(locale, "sim.form.type_label")}</label>
          <Segmented
            value={orderType}
            onChange={setOrderType}
            options={[
              { key: "market", label: t(locale, "sim.order_type.market"), active: "bg-tm-accent text-tm-bg" },
              { key: "limit", label: t(locale, "sim.order_type.limit"), active: "bg-tm-accent text-tm-bg" },
            ]}
          />
        </div>
        <div>
          <label className={FIELD_LABEL}>{t(locale, "sim.form.qty_label")}</label>
          <input
            type="number" min={1} step={1} value={qty}
            onChange={(e) => setQty(e.target.value)}
            className={clsx(INPUT, "w-24")}
          />
        </div>
        {orderType === "limit" && (
          <div>
            <label className={FIELD_LABEL}>{t(locale, "sim.form.limit_label")}</label>
            <input
              type="number" min={0.01} step={0.01} value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder="0.00"
              className={clsx(INPUT, "w-28")}
            />
          </div>
        )}
      </div>

      {/* Footer: buying power + estimate on the left, one primary action right */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-tm-rule pt-3">
        <div className="font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "sim.available_cash")}{" "}
          <span className="text-tm-fg-2">{cash !== null ? `$${FMT.format(cash)}` : "—"}</span>
          {estimatedCost !== null && (
            <>
              {"　"}
              {t(locale, "sim.estimated_cost")} <span className="text-tm-fg-2">≈ ${FMT.format(estimatedCost)}</span>
            </>
          )}
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded border border-tm-accent bg-tm-accent px-6 py-1.5 font-tm-mono text-[12px] font-semibold uppercase tracking-wide text-tm-bg transition-opacity hover:opacity-85 disabled:opacity-50"
        >
          {submitting ? t(locale, "sim.form.submitting") : t(locale, "sim.place_order")}
        </button>
      </div>

      {error && (
        <p className="rounded bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">{error}</p>
      )}
      {placed && (
        <div className="flex items-center gap-2 rounded bg-tm-pos/10 px-3 py-2 font-tm-mono text-[11px] text-tm-pos">
          <CheckCircle className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          {t(locale, "sim.form.order_placed")}
        </div>
      )}
    </form>
  );
}
