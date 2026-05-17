"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import {
  fetchMinuteBars,
  type MinuteBar,
  type MinuteBarsResponse,
} from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

// Modal that pops over the daily PriceChart when a user clicks a candle.
// Renders an intraday minute candlestick chart for the selected date.
// Mirrors the PriceChart.tsx lightweight-charts dynamic-import pattern but
// with a smaller surface (no SMA, no volume, no markers).
export default function IntradayDrawer({
  ticker,
  date,
  onClose,
}: {
  ticker: string;
  date: string | null;
  onClose: () => void;
}) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<
    "loading" | "ok" | "empty" | "out_of_range" | "error"
  >("loading");
  const [errMsg, setErrMsg] = useState<string>("");

  // ESC key closes the modal. Bound only while the modal is open
  // (date != null) to avoid leaking the listener on unmount.
  useEffect(() => {
    if (!date) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [date, onClose]);

  const renderChart = useCallback(async (bars: MinuteBar[]) => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = "";

    const { createChart, ColorType } = await import("lightweight-charts");

    const isLight = document.documentElement.dataset.theme === "light";
    const bg = isLight ? "#fafaf7" : "#0a0a0a";
    const text = isLight ? "#27272a" : "#d4d4d8";
    const grid = isLight ? "#e4e4e7" : "#27272a";

    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: text },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: grid },
      // Minute-level chart needs time-of-day on the axis.
      timeScale: { borderColor: grid, timeVisible: true, secondsVisible: false },
    });

    const validBars = bars.filter(
      (b): b is MinuteBar & {
        open: number;
        high: number;
        low: number;
        close: number;
      } =>
        b.open !== null && b.high !== null && b.low !== null && b.close !== null,
    );

    const candle = chart.addCandlestickSeries({
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    });
    candle.setData(
      validBars.map((b) => ({
        // lightweight-charts wants Unix seconds (UTCTimestamp) for
        // intraday series; ISO strings are only accepted for daily.
        time: (Math.floor(new Date(b.ts).getTime() / 1000)) as never,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!date) {
      setStatus("loading");
      return;
    }
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    (async () => {
      setStatus("loading");
      try {
        const r: MinuteBarsResponse = await fetchMinuteBars(ticker, date);
        if (cancelled) return;
        if (r.out_of_range) {
          setStatus("out_of_range");
          return;
        }
        if (!r.bars.length) {
          setStatus("empty");
          return;
        }
        setStatus("ok");
        // Defer to next tick so the canvas container has mounted with
        // status="ok" display:block before we measure clientWidth.
        await Promise.resolve();
        if (cancelled) return;
        cleanup = await renderChart(r.bars);
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        setErrMsg(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      cleanup?.();
    };
  }, [ticker, date, renderChart]);

  if (!date) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t(locale, "intraday.title")}
    >
      <div
        className="bg-tm-bg-2 border border-tm-rule rounded-lg p-4 w-[90vw] max-w-3xl h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold text-tm-fg">
            {ticker} {t(locale, "intraday.title")} · {date}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-tm-muted hover:text-tm-fg transition-colors"
            aria-label={t(locale, "intraday.close")}
          >
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 min-h-0 relative">
          {status === "loading" ? (
            <div className="h-full flex items-center justify-center text-sm text-tm-muted">
              {t(locale, "intraday.loading")}
            </div>
          ) : status === "empty" ? (
            <div className="h-full flex items-center justify-center text-sm text-tm-muted">
              {t(locale, "intraday.empty")}
            </div>
          ) : status === "out_of_range" ? (
            <div className="h-full flex items-center justify-center text-sm text-tm-muted">
              {t(locale, "intraday.out_of_range")}
            </div>
          ) : status === "error" ? (
            <div className="h-full flex items-center justify-center text-sm text-tm-neg">
              {t(locale, "intraday.error")}: {errMsg}
            </div>
          ) : null}
          <div
            ref={containerRef}
            style={{
              width: "100%",
              height: "100%",
              display: status === "ok" ? "block" : "none",
            }}
          />
        </div>
      </div>
    </div>
  );
}
