// frontend/src/components/picks/SimOrderDrawer.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { placeOrder, fetchPaperAccount} from "@/lib/api/paper";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import clsx from "clsx";

interface Props {
  readonly ticker: string;
  readonly card: RatingCard;
  readonly cash: number;
  readonly onClose: () => void;
  readonly onOrderPlaced: () => void;
}

export default function SimOrderDrawer({ ticker, card, cash, onClose, onOrderPlaced }: Props) {
  const { locale } = useLocale();
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [qty, setQty] = useState<string>("10");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Self-fetch the live account cash: the drawer is opened from the picks
  // table where the caller does not have the balance, so relying on the
  // `cash` prop alone showed a misleading $0. Falls back to the prop.
  const [liveCash, setLiveCash] = useState<number | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Suppress unused-variable warning; card is available for future price display
  void card;

  useEffect(() => {
    let cancelled = false;
    fetchPaperAccount()
      .then((a) => { if (!cancelled) setLiveCash(a.cash); })
      .catch(() => { /* keep the prop fallback */ });
    return () => { cancelled = true; };
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const qtyNum = parseInt(qty, 10);
  const limitNum = parseFloat(limitPrice);
  const estimatedCost = !isNaN(qtyNum) && orderType === "limit" && !isNaN(limitNum)
    ? qtyNum * limitNum
    : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (isNaN(qtyNum) || qtyNum <= 0) {
      setError(locale === "zh" ? "数量必须大于0" : "Qty must be > 0");
      return;
    }
    if (orderType === "limit" && (isNaN(limitNum) || limitNum <= 0)) {
      setError(locale === "zh" ? "限价必须大于0" : "Limit price must be > 0");
      return;
    }
    setSubmitting(true);
    try {
      await placeOrder({
        ticker,
        side,
        order_type: orderType,
        qty: qtyNum,
        ...(orderType === "limit" ? { limit_price: limitNum } : {}),
      });
      onOrderPlaced();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={locale === "zh" ? "模拟下单" : "Simulated Order"}
        className="fixed right-0 top-0 z-50 flex h-full w-80 flex-col border-l border-tm-rule bg-tm-bg shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-tm-rule px-4 py-3">
          <div>
            <span className="font-tm-mono text-[15px] font-bold text-tm-fg">{ticker}</span>
            <span
              className={clsx(
                "ml-2 font-tm-mono text-[11px] font-semibold uppercase",
                side === "buy" ? "text-tm-pos" : "text-tm-neg",
              )}
            >
              {side === "buy" ? t(locale, "sim.order_side.buy") : t(locale, "sim.order_side.sell")}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-tm-muted hover:text-tm-fg text-lg leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
          {/* Side */}
          <div>
            <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
              {locale === "zh" ? "方向" : "Side"}
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
              {locale === "zh" ? "类型" : "Type"}
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

          {/* Qty */}
          <div>
            <label className="mb-1 block font-tm-mono text-[10px] uppercase tracking-wide text-tm-muted">
              {locale === "zh" ? "数量（股）" : "Quantity (shares)"}
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
                {locale === "zh" ? "限价" : "Limit Price"}
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
                <span>≈ ${estimatedCost.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>
              </div>
            )}
            <div className="flex justify-between text-tm-muted">
              <span>{t(locale, "sim.available_cash")}</span>
              <span>${(liveCash ?? cash).toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>
            </div>
          </div>

          {error && (
            <p className="rounded bg-tm-neg/10 px-3 py-2 font-tm-mono text-[11px] text-tm-neg">
              {error}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting}
            className="mt-auto w-full rounded border border-tm-accent bg-tm-accent py-2 font-tm-mono text-[12px] font-semibold uppercase tracking-wide text-tm-bg transition-opacity disabled:opacity-50"
          >
            {submitting
              ? (locale === "zh" ? "提交中..." : "Submitting...")
              : t(locale, "sim.place_order")}
          </button>

          {/* Disclaimer */}
          <p className="text-center font-tm-mono text-[10px] leading-snug text-tm-muted">
            ⚠ {t(locale, "sim.disclaimer")}
          </p>
        </form>
      </div>
    </>
  );
}
