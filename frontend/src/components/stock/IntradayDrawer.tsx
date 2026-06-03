"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import {
  fetchMinuteBars,
  type ChartEvent,
  type MinuteBar,
  type MinuteBarsResponse,
} from "@/lib/api/picks";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

// Inline panel (was a modal) that opens BELOW the daily PriceChart when a user
// clicks a candle: the day's intraday minute chart + a scrollable list of that
// day's news/events. Inline (not a popup) per the 2026-06-02 redesign.
// Renders an intraday minute candlestick chart for the selected date.
// Mirrors the PriceChart.tsx lightweight-charts dynamic-import pattern but
// with a smaller surface (no SMA, no volume, no markers).
export default function IntradayDrawer({
  ticker,
  date,
  onClose,
  news = [],
}: {
  ticker: string;
  date: string | null;
  onClose: () => void;
  // That day's events (news + macro), already filtered by the parent, shown as
  // a scrollable list below the intraday chart.
  news?: ChartEvent[];
}) {
  const { locale } = useLocale();

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
      const w = el.clientWidth;
      if (w === 0) return;
      chart.applyOptions({ width: w, height: el.clientHeight });
      // Re-fit on every width change. The panel mounts inline and its first
      // measured width can be too small (layout not settled), which left the
      // bars crammed against the right edge; without re-fitting they never
      // spread. Mirrors PriceChart's resize handler.
      chart.timeScale().fitContent();
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
    <div className="mt-3 rounded border border-tm-rule bg-tm-bg-2 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-tm-fg">
          {ticker} {t(locale, "intraday.title")} · {date}
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="text-tm-muted transition-colors hover:text-tm-fg"
          aria-label={t(locale, "intraday.close")}
        >
          <X size={18} />
        </button>
      </div>

      {/* intraday minute chart */}
      <div className="relative" style={{ width: "100%", height: 280 }}>
        {status === "loading" ? (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "intraday.loading")}
          </div>
        ) : status === "empty" ? (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "intraday.empty")}
          </div>
        ) : status === "out_of_range" ? (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-tm-muted">
            {t(locale, "intraday.out_of_range")}
          </div>
        ) : status === "error" ? (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-tm-neg">
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

      {/* that day's news / events */}
      <div className="mt-3 border-t border-tm-rule pt-3">
        <div className="mb-1.5 font-tm-sans text-[11px] uppercase tracking-wide text-tm-muted">
          {t(locale, "intraday.news_title")} · {news.length}
        </div>
        {news.length === 0 ? (
          <div className="py-2 text-xs text-tm-muted">
            {t(locale, "intraday.news_empty")}
          </div>
        ) : (
          <ul className="max-h-[300px] space-y-1.5 overflow-y-auto pr-1">
            {news.map((e, i) => {
              const s = e.sentiment_score ?? 0;
              const tone =
                s > 0.1
                  ? { pill: "bg-tm-pos/15 text-tm-pos", label: t(locale, "intraday.sent_pos") }
                  : s < -0.1
                    ? { pill: "bg-tm-neg/15 text-tm-neg", label: t(locale, "intraday.sent_neg") }
                    : { pill: "bg-tm-muted/15 text-tm-muted", label: t(locale, "intraday.sent_neu") };
              const src = hostname(e.url);
              const tod = timeOfDay(e.ts);
              // The whole card is the click target (feed-like), not just the
              // headline text, so the hover affordance covers the full row.
              const cardClass =
                "group block rounded-md border border-tm-rule/60 bg-tm-bg-3/30 px-3 py-2 transition-colors hover:border-tm-accent/50 hover:bg-tm-bg-3";
              const body = (
                <>
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tone.pill}`}
                    >
                      {tone.label}
                    </span>
                    {tod ? (
                      <span className="font-tm-mono text-[11px] text-tm-muted">
                        {tod}
                      </span>
                    ) : null}
                    {src ? (
                      <span className="truncate text-[11px] text-tm-muted">
                        · {src}
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[13px] leading-snug text-tm-fg transition-colors group-hover:text-tm-accent">
                    {e.headline}
                  </div>
                </>
              );
              return (
                <li key={`${e.ts}-${i}`}>
                  {e.url ? (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cardClass}
                    >
                      {body}
                    </a>
                  ) : (
                    <div className={cardClass}>{body}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// Bare domain from a URL for the source label, e.g. "reuters.com".
function hostname(u: string | null): string | null {
  if (!u) return null;
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

// Local time-of-day ("HH:mm") for a news event timestamp. Null when the
// timestamp is missing or unparseable so the caller can omit it.
function timeOfDay(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
