"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MousePointerClick } from "lucide-react";
import type { ChartEvent, OhlcvBar } from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import IntradayDrawer from "./IntradayDrawer";
import ExplainRangePanel from "./ExplainRangePanel";

// lightweight-charts v4 imports — keep dynamic to avoid SSR breakage (the
// lib touches `document` at import time). The component itself is
// client-only via "use client".
//
// Tier 4 #1 (2026-05-19): OHLCV + event data moved to RSC; this component
// no longer fetches anything. Pure renderer over the bars/events props
// the parent page resolved in its Promise.all.

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

export default function PriceChart({
  ticker,
  bars,
  events,
}: {
  ticker: string;
  bars: OhlcvBar[];
  events: ChartEvent[];
}) {
  const { locale } = useLocale();

  const containerRef = useRef<HTMLDivElement | null>(null);
  // Floating crosshair tooltip that surfaces the hovered day's news headlines
  // (replaces the old per-marker text labels that piled up unreadably).
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "empty" | "error">("loading");
  const [errMsg, setErrMsg] = useState<string>("");
  // YYYY-MM-DD of the daily candle the user clicked; null = drawer closed.
  const [drawerDate, setDrawerDate] = useState<string | null>(null);
  // Stable reference so IntradayDrawer's keydown-listener effect does not
  // tear down + re-bind on every PriceChart render (e.g. status changes).
  const handleDrawerClose = useCallback(() => setDrawerDate(null), []);

  const renderChart = useCallback(async (bars: OhlcvBar[], events: ChartEvent[]) => {
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

    // B4 (2026-05-19, decluttered 2026-05-31): event markers per type, anchored
    // to the candle series so they sit on the day's price. CLEAN SHAPES ONLY —
    // the old per-marker `text: headline` piled long labels on top of each
    // other (unreadable when several events cluster near the latest bars). The
    // headline now lives in a crosshair-hover tooltip instead.
    //   news               = aboveBar circle
    //   macro_political    = belowBar square
    //   macro_geopolitical = belowBar arrowDown
    // colour by sentiment (green/red/neutral).
    const eventsByDay = new Map<string, ChartEvent[]>();
    if (events.length) {
      const dayBars = new Set(validBars.map((b) => b.date));
      const markers = events
        .map((e) => {
          const day = e.ts.slice(0, 10);
          if (!dayBars.has(day)) return null;
          const list = eventsByDay.get(day) ?? [];
          list.push(e);
          eventsByDay.set(day, list);
          const sentiment = e.sentiment_score ?? 0;
          const color = sentiment > 0.1 ? "#16a34a" : sentiment < -0.1 ? "#dc2626" : "#9ca3af";
          const shape =
            e.type === "news" ? "circle"
            : e.type === "macro_political" ? "square"
            : "arrowDown";
          const position = e.type === "news" ? "aboveBar" : "belowBar";
          return {
            time: day,
            position: position as "aboveBar" | "belowBar",
            color,
            shape: shape as "circle" | "square" | "arrowDown",
            // no text — keeps the chart clean; headline surfaces on hover
          };
        })
        .filter((m): m is NonNullable<typeof m> => m !== null);
      candle.setMarkers(markers);
    }

    // Crosshair-hover tooltip: show the hovered day's headlines (if any) in a
    // floating box near the cursor. De-dupes by day so a cluster reads as one
    // compact list instead of overlapping labels.
    const tip = tooltipRef.current;
    chart.subscribeCrosshairMove((param) => {
      if (!tip) return;
      const day = typeof param.time === "string" ? param.time : null;
      const dayEvents = day ? eventsByDay.get(day) : undefined;
      if (!day || !dayEvents || !param.point) {
        tip.style.display = "none";
        return;
      }
      const shown = dayEvents.slice(0, 4);
      const more = dayEvents.length - shown.length;
      const rows = shown
        .map((e) => {
          const s = e.sentiment_score ?? 0;
          const dot = s > 0.1 ? "#16a34a" : s < -0.1 ? "#dc2626" : "#9ca3af";
          const safe = e.headline
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          return `<div style="display:flex;gap:6px;align-items:flex-start;margin-top:2px">
            <span style="flex:none;width:6px;height:6px;border-radius:50%;background:${dot};margin-top:4px"></span>
            <span>${safe}</span></div>`;
        })
        .join("");
      tip.innerHTML =
        `<div style="color:${text};opacity:0.6;margin-bottom:2px">${day}</div>${rows}` +
        (more > 0 ? `<div style="opacity:0.5;margin-top:2px">+${more}</div>` : "");
      tip.style.display = "block";
      // Clamp x so the box stays inside the chart; flip above if near bottom.
      const w = el.clientWidth;
      const left = Math.min(Math.max(param.point.x + 12, 4), w - 248);
      tip.style.left = `${left}px`;
      tip.style.top = `${Math.max(param.point.y - 8, 4)}px`;
    });

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

    // Resize handler. TradingView doesn't auto-resize. Re-fit content on every
    // width change — critical because the very first measurement can be 0 (the
    // container starts hidden); without re-fitting, bar spacing stays computed
    // for width≈0 and the candles cram into the right edge.
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w === 0) return;
      chart.applyOptions({ width: w });
      chart.timeScale().fitContent();
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, []);

  // Bars + events arrive as props from the RSC; we still need a client
  // effect to: (a) dynamic-import lightweight-charts (touches `document`
  // at import-time → can't SSR), (b) measure the container's clientWidth,
  // (c) bind ResizeObserver. No network IO here anymore.
  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;
    (async () => {
      if (!bars.length) {
        setStatus("empty");
        return;
      }
      setStatus("loading");
      try {
        cleanup = await renderChart(bars, events);
        if (cancelled) {
          cleanup?.();
          return;
        }
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
  }, [bars, events, renderChart]);

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-tm-fg">
          {t(locale, "chart.title")} · {ticker}
        </h2>
        {status === "ok" ? (
          <div className="inline-flex items-center gap-1.5 rounded-md border border-tm-accent/30 bg-tm-accent/10 px-2.5 py-1 text-sm text-tm-accent">
            <MousePointerClick className="h-4 w-4" strokeWidth={1.75} />
            <span className="font-medium">
              {t(locale, "chart.click_for_intraday")}
            </span>
          </div>
        ) : null}
      </div>
      {/* Fixed-height parent. The chart container stays mounted at full width
          ALWAYS (never display:none) so lightweight-charts measures a real
          clientWidth at init — hiding it made the first measurement 0 and the
          candles crammed right. Status overlays sit absolutely on top.
          (CLAUDE.md memory feedback_recharts_responsive_container_zero_width.md) */}
      <div className="relative" style={{ width: "100%", height: 320 }}>
        <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
        {/* crosshair news tooltip */}
        <div
          ref={tooltipRef}
          className="pointer-events-none absolute z-10 hidden max-w-[240px] rounded border border-tm-rule bg-tm-bg-2/95 px-2 py-1.5 font-tm-mono text-[10.5px] leading-snug text-tm-fg shadow-lg shadow-black/30"
        />
        {status !== "ok" ? (
          <div className="absolute inset-0 flex items-center justify-center bg-tm-bg-2">
            {status === "loading" ? (
              <span className="text-sm text-tm-muted">{t(locale, "chart.loading")}</span>
            ) : status === "empty" ? (
              <span className="text-sm text-tm-muted">{t(locale, "chart.no_data")}</span>
            ) : (
              <span className="text-sm text-tm-neg">
                {t(locale, "chart.error").replace("{reason}", errMsg)}
              </span>
            )}
          </div>
        ) : null}
      </div>
      <IntradayDrawer
        ticker={ticker}
        date={drawerDate}
        onClose={handleDrawerClose}
      />
      {status === "ok" ? <ExplainRangePanel ticker={ticker} /> : null}
    </section>
  );
}
