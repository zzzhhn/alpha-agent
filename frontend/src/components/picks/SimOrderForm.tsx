// frontend/src/components/picks/SimOrderForm.tsx
"use client";

/**
 * SimOrderForm — reusable order-ticket form.
 *
 * Used by:
 *  - SimOrderDrawer (ticker is fixed, passed as prop)
 *  - PaperTab "下单" tab (ticker is editable when no fixedTicker given)
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

  // Fetch live cash on mount
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

    if (!effectiveTicker) {
      setError(t(locale, "sim.form.ticker_required"));
      return;
    }
    if (isNaN(qtyNum) || qtyNum <= 0) {
      setError(t(locale, "sim.form.qty_error"));
      return;
    }
    if (orderType === "limit" && (isNaN(limitNum) || limitNum <= 0)) {
      setError(t(locale, "sim.form.limit_error"));
      return;
    }

    setSubmitting(true);
    try {
      await placeOrder({
        ticker: effectiveTicker,
        side,
        order_type: orderType,
        qty: qtyNum,
        ...(orderType === "limit" ? { limit_price: limitNum } : {}),
      });
      setPlaced(true);
      // Refresh cash after placing
      fetchPaperAccount()
        .then((a) => setCash(a.cash))
        .catch(() => { /* ignore */ });
      onPlaced();
      // Auto-reset placed state after 2 s
      setTimeout(() => setPlaced(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {/* Ticker input — only when no fixed ticker */}
      {!fixedTicker && (
        <div>
          <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
            {t(locale, "sim.form.ticker_label")}
          </label>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            className="w-full rounded border border-tm-rule bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-sm uppercase text-tm-fg placeholder:normal-case placeholder:text-tm-muted focus:border-tm-accent focus:outline-none"
          />
        </div>
      )}

      {/* Fixed ticker display */}
      {fixedTicker && (
        <div className="flex items-baseline gap-2">
          <span className="font-tm-mono text-[15px] font-bold text-tm-fg">{fixedTicker}</span>
          <span
            className={clsx(
              "font-tm-mono text-[11px] font-semibold uppercase",
              side === "buy" ? "text-tm-pos" : "text-tm-neg",
            )}
          >
            {side === "buy" ? t(locale, "sim.order_side.buy") : t(locale, "sim.order_side.sell")}
          </span>
        </div>
      )}

      {/* Side */}
      <div>
        <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
          {t(locale, "sim.form.side_label")}
        </label>
        <div className="flex gap-2">
          {(["buy", "sell"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={clsx(
                "flex-1 rounded border py-1.5 font-tm-mono text-[11px] font-semibold uppercase transition-colors",
                side === s && s === "buy"
                  ? "border-tm-pos bg-tm-pos text-tm-bg"
                  : side === s && s === "sell"
                    ? "border-tm-neg bg-tm-neg text-tm-bg"
                    : "border-tm-rule text-tm-muted hover:border-tm-fg hover:text-tm-fg",
              )}
            >
              {t(locale, `sim.order_side.${s}` as "sim.order_side.buy")}
            </button>
          ))}
        </div>
      </div>

      {/* Order type */}
      <div>
        <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
          {t(locale, "sim.form.type_label")}
        </label>
        <div className="flex gap-2">
          {(["market", "limit"] as const).map((ot) => (
            <button
              key={ot}
              type="button"
              onClick={() => setOrderType(ot)}
              className={clsx(
                "flex-1 rounded border py-1.5 font-tm-mono text-[11px] font-semibold uppercase transition-colors",
                orderType === ot
                  ? "border-tm-accent bg-tm-accent text-tm-bg"
                  : "border-tm-rule text-tm-muted hover:border-tm-fg hover:text-tm-fg",
              )}
            >
              {t(locale, `sim.order_type.${ot}` as "sim.order_type.market")}
            </button>
          ))}
        </div>
      </div>

      {/* Quantity */}
      <div>
        <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
          {t(locale, "sim.form.qty_label")}
        </label>
        <input
          type="number"
          min={1}
          step={1}
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="w-full rounded border border-tm-rule bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-sm text-tm-fg focus:border-tm-accent focus:outline-none"
        />
      </div>

      {/* Limit price (conditional) */}
      {orderType === "limit" && (
        <div>
          <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
            {t(locale, "sim.form.limit_label")}
          </label>
          <input
            type="number"
            min={0.01}
            step={0.01}
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            placeholder="0.00"
            className="w-full rounded border border-tm-rule bg-tm-bg-2 px-2 py-1.5 font-tm-mono text-sm text-tm-fg focus:border-tm-accent focus:outline-none"
          />
        </div>
      )}

      {/* Cost estimate + cash */}
      <div className="rounded bg-tm-bg-2 px-3 py-2.5 text-[11px] font-tm-mono">
        {estimatedCost !== null && (
          <div className="flex justify-between text-tm-fg-2">
            <span>{t(locale, "sim.estimated_cost")}</span>
            <span>≈ ${FMT.format(estimatedCost)}</span>
          </div>
        )}
        <div className="flex justify-between text-tm-muted">
          <span>{t(locale, "sim.available_cash")}</span>
          <span>{cash !== null ? `$${FMT.format(cash)}` : "—"}</span>
        </div>
      </div>

      {error && (
        <p className="rounded bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
          {error}
        </p>
      )}

      {/* Success confirmation */}
      {placed && (
        <div className="flex items-center gap-2 rounded bg-tm-pos/10 px-3 py-2 font-tm-mono text-[11px] text-tm-pos">
          <CheckCircle className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          {t(locale, "sim.form.order_placed")}
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded border border-tm-accent bg-tm-accent py-2.5 font-tm-mono text-[12px] font-semibold uppercase tracking-wide text-tm-bg transition-opacity disabled:opacity-50"
      >
        {submitting
          ? t(locale, "sim.form.submitting")
          : t(locale, "sim.place_order")}
      </button>

      {/* Disclaimer */}
      <p className="text-center font-tm-mono text-[10px] leading-snug text-tm-muted">
        {t(locale, "sim.disclaimer")}
      </p>
    </form>
  );
}
