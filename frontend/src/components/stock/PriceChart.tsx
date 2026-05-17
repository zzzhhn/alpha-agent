"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchOhlcv, type OhlcvBar } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import IntradayDrawer from "./IntradayDrawer";

// lightweight-charts v4 imports — keep dynamic to avoid SSR breakage (the
// lib touches `document` at import time). The component itself is
// client-only via "use client".

function sma(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i >= window - 1 ? sum / window : null);
  }
  return out;
}

export default function PriceChart({ ticker }: { ticker: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "empty" | "error">("loading");
  const [errMsg, setErrMsg] = useState<string>("");
  // YYYY-MM-DD of the daily candle the user clicked; null = drawer closed.
  const [drawerDate, setDrawerDate] = useState<string | null>(null);

  const renderChart = useCallback(async (bars: OhlcvBar[]) => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = "";

    const { createChart, ColorType } = await import("lightweight-charts");

    // Resolve theme from data-theme attribute (set globally by ThemeProvider).
    const isLight = document.documentElement.dataset.theme === "light";
    const bg = isLight ? "#fafaf7" : "#0a0a0a";
    const text = isLight ? "#27272a" : "#d4d4d8";
    const grid = isLight ? "#e4e4e7" : "#27272a";

    const chart = createChart(el, {
      width: el.clientWidth,
      height: 320,
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: text },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      rightPriceScale: { borderColor: grid },
      timeScale: { borderColor: grid, timeVisible: false },
    });

    // Filter out bars with null prices (yfinance gaps); chart consumer drops them.
    const validBars = bars.filter(
      (b): b is OhlcvBar & { open: number; high: number; low: number; close: number } =>
        b.open !== null && b.high !== null && b.low !== null && b.close !== null
    );

    const candle = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
    });
    candle.setData(
      validBars.map((b) => ({ time: b.date, open: b.open, high: b.high, low: b.low, close: b.close }))
    );

    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      validBars.map((b) => ({
        time: b.date,
        value: b.volume,
        color: b.close >= b.open ? "rgba(22,163,74,0.4)" : "rgba(220,38,38,0.4)",
      }))
    );

    const smaValues = sma(validBars.map((b) => b.close), 50);
    const ma = chart.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false });
    ma.setData(
      validBars
        .map((b, i) => ({ time: b.date, value: smaValues[i] }))
        .filter((p): p is { time: string; value: number } => p.value !== null)
    );

    chart.timeScale().fitContent();

    // Daily-candle click handler: open the IntradayDrawer for that date.
    // lightweight-charts v4 reports param.time as either a string
    // ("YYYY-MM-DD" for BusinessDay-shaped data) or a number (Unix
    // seconds for UTCTimestamp data). For our daily series we set
    // `time` as YYYY-MM-DD strings above so the string branch is the
    // hot path; the number branch is defensive.
    chart.subscribeClick((param) => {
      if (!param.time) return;
      let dateStr: string;
      if (typeof param.time === "string") {
        dateStr = param.time;
      } else if (typeof param.time === "number") {
        const d = new Date(param.time * 1000);
        dateStr = d.toISOString().slice(0, 10);
      } else {
        return;
      }
      setDrawerDate(dateStr);
    });

    // Resize handler. TradingView doesn't auto-resize.
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    (async () => {
      setStatus("loading");
      try {
        const r = await fetchOhlcv(ticker);
        if (cancelled) return;
        if (!r.bars.length) {
          setStatus("empty");
          return;
        }
        cleanup = await renderChart(r.bars);
        setStatus("ok");
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
  }, [ticker, renderChart]);

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "chart.title")} · {ticker}
      </h2>
      {/* Fixed-height parent: lightweight-charts reads offsetWidth/Height at
          init; collapsing to 0 in a flex/grid parent kills the canvas
          (CLAUDE.md memory feedback_recharts_responsive_container_zero_width.md). */}
      <div style={{ width: "100%", height: 320 }}>
        {status === "loading" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "chart.loading")}
          </div>
        ) : status === "empty" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "chart.no_data")}
          </div>
        ) : status === "error" ? (
          <div className="h-full flex items-center justify-center text-sm text-tm-neg">
            {t(locale, "chart.error").replace("{reason}", errMsg)}
          </div>
        ) : null}
        <div ref={containerRef} style={{ width: "100%", height: "100%", display: status === "ok" ? "block" : "none" }} />
      </div>
      {status === "ok" ? (
        <p className="mt-2 text-xs text-tm-muted">
          {t(locale, "chart.click_for_intraday")}
        </p>
      ) : null}
      <IntradayDrawer
        ticker={ticker}
        date={drawerDate}
        onClose={() => setDrawerDate(null)}
      />
    </section>
  );
}
