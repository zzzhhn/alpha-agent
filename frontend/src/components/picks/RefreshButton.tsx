"use client";
//
// Client-side "Refresh now" button + last-refresh badge for the picks page.
// Dispatches the cron-shards GH Actions workflow via /api/admin/refresh.
// The dispatch is asynchronous: /api/admin/refresh returns immediately with
// an eta_minutes estimate, and the fresh data only lands when the cron run
// finishes. To give the user a sense of "how much longer", a successful
// dispatch shows an ETA countdown bar driven purely by elapsed wall-clock
// time against eta_minutes (no real per-ticker progress signal exists).
import { useCallback, useEffect, useState } from "react";
import { triggerRefresh, fetchLastRefresh } from "@/lib/api/admin";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import {
  DISPATCH_EVENT,
  loadDispatch,
  saveDispatch,
} from "@/lib/dispatch-state";

function formatAge(iso: string | null, locale: "zh" | "en"): string {
  if (!iso) return locale === "zh" ? "暂无" : "never";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return locale === "zh" ? "刚刚" : "just now";
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

type ToastState =
  | { kind: "idle" }
  | { kind: "pending" }
  | { kind: "ok"; min: number }
  | { kind: "cooldown" }
  | { kind: "no_token" }
  | { kind: "failed"; reason: string };

// ETA countdown bar shown after a successful dispatch. pct is clamped 0..1;
// `done` means the estimated window has elapsed (fresh data should be in,
// reload to see it).
function DispatchProgress({
  pct,
  remainingMin,
  done,
  locale,
}: {
  pct: number;
  remainingMin: number;
  done: boolean;
  locale: "zh" | "en";
}) {
  const label = done
    ? locale === "zh"
      ? "数据已更新"
      : "data updated"
    : locale === "zh"
      ? `预计还需 ${remainingMin} 分钟`
      : `about ${remainingMin} min remaining`;
  return (
    <div className="flex w-56 flex-col gap-1">
      <div className="h-1.5 w-full overflow-hidden rounded bg-tm-bg-3">
        <div
          className={`h-full transition-[width] duration-1000 ease-linear ${done ? "bg-tm-pos" : "bg-tm-accent"}`}
          style={{ width: `${Math.round(pct * 100)}%` }}
        />
      </div>
      <span className={`text-[11px] ${done ? "text-tm-pos" : "text-tm-muted"}`}>
        {label}
      </span>
    </div>
  );
}

export default function RefreshButton() {
  const { locale } = useLocale();
  const [toast, setToast] = useState<ToastState>({ kind: "idle" });
  const [lastRun, setLastRun] = useState<string | null>(null);
  // Dispatch ETA tracking: when a dispatch succeeds we record the wall-clock
  // start + the eta estimate, and `now` ticks once a second so the bar fills.
  const [dispatchedAt, setDispatchedAt] = useState<number | null>(null);
  const [etaMin, setEtaMin] = useState(18);
  const [now, setNow] = useState(() => Date.now());

  // Rehydrate any in-flight dispatch ETA from localStorage so the countdown
  // bar survives a page refresh; loadDispatch drops anything beyond the ETA
  // + 30min grace window.
  useEffect(() => {
    const saved = loadDispatch();
    if (saved != null) {
      setEtaMin(saved.etaMin);
      setDispatchedAt(saved.at);
    }
  }, []);

  // Keep the "X min ago" badge current. P3-1: the timestamp itself only
  // changes when a cron runs (a few times/day), and /last_refresh is a slow
  // round-trip (Neon cold connection, ~1-2s for 100 bytes). So fetch the
  // timestamp once + re-fetch only every 5 min, while ticking a local clock
  // every 60s so the badge text increments WITHOUT a network call. Net:
  // ~5x fewer /last_refresh round-trips, badge stays live.
  useEffect(() => {
    let cancelled = false;
    const fetchAge = async () => {
      try {
        const r = await fetchLastRefresh();
        if (!cancelled) setLastRun(r.fast_intraday);
      } catch {
        // Silent: the badge just won't update, not worth surfacing.
      }
    };
    fetchAge();
    const fetchId = setInterval(fetchAge, 300_000); // re-fetch every 5 min
    const tickId = setInterval(() => {
      if (!cancelled) setNow(Date.now()); // local re-render → fmtAge recomputes
    }, 60_000);
    return () => {
      cancelled = true;
      clearInterval(fetchId);
      clearInterval(tickId);
    };
  }, []);

  // Tick `now` every second while a dispatch ETA is in flight; stop ticking
  // once the estimated window has elapsed (the bar is full from then on).
  useEffect(() => {
    if (dispatchedAt == null) return;
    const totalMs = etaMin * 60_000;
    setNow(Date.now());
    const id = setInterval(() => {
      const tNow = Date.now();
      setNow(tNow);
      if (tNow - dispatchedAt >= totalMs) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [dispatchedAt, etaMin]);

  const onClick = useCallback(async () => {
    setToast({ kind: "pending" });
    let dispatched = false;
    try {
      const r = await triggerRefresh("fast_intraday");
      if (r.ok) {
        const eta = r.eta_minutes ?? 18;
        const at = Date.now();
        setToast({ kind: "ok", min: eta });
        if (r.dispatched_at) setLastRun(r.dispatched_at);
        setEtaMin(eta);
        setDispatchedAt(at);
        saveDispatch(at, eta);
        // Tell PicksBrowser (same tab) to snapshot + freeze the board now.
        window.dispatchEvent(new CustomEvent(DISPATCH_EVENT));
        dispatched = true;
      } else if (r.reason?.toLowerCase().includes("cooldown")) {
        setToast({ kind: "cooldown" });
      } else if (r.reason?.toLowerCase().includes("gh_pat")) {
        setToast({ kind: "no_token" });
      } else {
        setToast({ kind: "failed", reason: r.reason ?? "unknown" });
      }
    } catch (e) {
      setToast({
        kind: "failed",
        reason: e instanceof Error ? e.message : String(e),
      });
    }
    // Transient toasts auto-clear after 6s. A successful dispatch instead
    // keeps its ETA progress bar alive until the window elapses.
    if (!dispatched) {
      setTimeout(() => setToast({ kind: "idle" }), 6000);
    }
  }, []);

  const ageLabel = formatAge(lastRun, locale);
  const pending = toast.kind === "pending";

  // ETA progress, derived from elapsed wall-clock time vs the estimate.
  const progress = (() => {
    if (dispatchedAt == null) return null;
    const totalMs = etaMin * 60_000;
    const elapsedMs = now - dispatchedAt;
    const pct = Math.min(Math.max(elapsedMs / totalMs, 0), 1);
    const remainingMin = Math.max(Math.ceil((totalMs - elapsedMs) / 60_000), 0);
    return { pct, remainingMin, done: pct >= 1 };
  })();
  // Lock the button for the WHOLE estimated window, not just the brief
  // dispatch HTTP call — re-clicking mid-window used to fire a second cron
  // dispatch (the user's complaint), not a page refresh.
  const inFlight = progress != null && !progress.done;
  const btnPct = inFlight && progress ? Math.round(progress.pct * 100) : 0;

  // The "ok" state is represented by the progress bar, so only non-ok
  // toasts render as a text span.
  const toastText = (() => {
    switch (toast.kind) {
      case "pending":
        return t(locale, "picks.refresh.pending");
      case "cooldown":
        return t(locale, "picks.refresh.cooldown");
      case "no_token":
        return t(locale, "picks.refresh.no_token");
      case "failed":
        return t(locale, "picks.refresh.failed").replace("{reason}", toast.reason);
      default:
        return null;
    }
  })();
  const toastTone =
    toast.kind === "failed" || toast.kind === "no_token"
      ? "text-tm-neg"
      : toast.kind === "cooldown"
        ? "text-tm-warn"
        : "text-tm-muted";

  return (
    <div className="flex flex-col items-end gap-1.5 text-xs">
      <div className="flex items-center gap-3">
        <span className="text-tm-muted">
          {t(locale, "picks.lastrun")}:{" "}
          <span className="text-tm-fg-2">{ageLabel}</span>
        </span>
        <button
          type="button"
          onClick={onClick}
          disabled={pending || inFlight}
          title={inFlight ? t(locale, "picks.refresh.inflight_tip") : undefined}
          className="rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 text-tm-fg hover:border-tm-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {inFlight
            ? `${t(locale, "picks.refresh.inflight")} ${btnPct}%`
            : t(locale, pending ? "picks.refresh.pending" : "picks.refresh")}
        </button>
        {toastText ? (
          <span className={`text-xs ${toastTone}`}>{toastText}</span>
        ) : null}
      </div>
      {progress ? (
        <DispatchProgress
          pct={progress.pct}
          remainingMin={progress.remainingMin}
          done={progress.done}
          locale={locale}
        />
      ) : null}
    </div>
  );
}
