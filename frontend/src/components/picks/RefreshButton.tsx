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
import { TmButton } from "@/components/tm/TmButton";
import { useAdminAccess } from "@/components/layout/SystemHealth";
import {
  clearDispatch,
  DISPATCH_EVENT,
  loadDispatch,
  REFRESH_SETTLED_EVENT,
  saveDispatch,
  type RefreshSettledDetail,
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
// `done` means only that the ETA elapsed. It never claims publication success;
// that requires a terminal recommendation_publish record from the backend.
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
      ? "预计时间已到，正在确认快照发布结果"
      : "ETA elapsed; verifying snapshot publication"
    : locale === "zh"
      ? `预计还需 ${remainingMin} 分钟`
      : `about ${remainingMin} min remaining`;
  return (
    <div className="flex w-56 flex-col gap-1">
      <div className="h-1.5 w-full overflow-hidden rounded-[2px] bg-tm-bg-3">
        <div
          className={`h-full transition-[width] duration-1000 ease-linear ${done ? "bg-tm-warn" : "bg-tm-accent"}`}
          style={{ width: `${Math.round(pct * 100)}%` }}
        />
      </div>
      <span className={`text-xs ${done ? "text-tm-warn" : "text-tm-muted"}`}>
        {label}
      </span>
    </div>
  );
}

export default function RefreshButton() {
  const isAdmin = useAdminAccess();
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
        if (!cancelled) {
          setLastRun(r.fast_intraday_finished_at ?? r.fast_intraday);
        }
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

  // Tick through the bounded verification grace period. ETA completion is not
  // a success signal, so the button remains locked until publish settles.
  useEffect(() => {
    if (dispatchedAt == null) return;
    const maxMs = (etaMin + 30) * 60_000;
    setNow(Date.now());
    const id = setInterval(() => {
      const tNow = Date.now();
      setNow(tNow);
      if (tNow - dispatchedAt >= maxMs) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [dispatchedAt, etaMin]);

  // Poll the backend's terminal publish audit. This is the only path allowed
  // to announce completion; cron start time and elapsed ETA are not evidence
  // that an immutable recommendation snapshot changed.
  useEffect(() => {
    if (dispatchedAt == null) return;
    let cancelled = false;

    const pollPublish = async () => {
      const dispatch = loadDispatch();
      if (!dispatch) {
        if (!cancelled) {
          const detail: RefreshSettledDetail = {
            status: "failed",
            runId: null,
            marketDate: null,
          };
          window.dispatchEvent(
            new CustomEvent(REFRESH_SETTLED_EVENT, { detail }),
          );
          setDispatchedAt(null);
        }
        return;
      }
      try {
        const response = await fetchLastRefresh();
        if (cancelled) return;
        setLastRun(
          response.fast_intraday_finished_at ?? response.fast_intraday,
        );
        const published = response.recommendation_publish;
        if (!published?.finished_at) return;
        if (
          dispatch.requestId != null &&
          published.request_id !== dispatch.requestId
        ) {
          return;
        }
        const dispatchMs = Date.parse(
          dispatch.serverDispatchedAt ?? new Date(dispatch.at).toISOString(),
        );
        const publishMs = Date.parse(published.finished_at);
        if (!Number.isFinite(publishMs) || publishMs < dispatchMs) return;

        const detail: RefreshSettledDetail = {
          status: published.status,
          runId: published.run_id,
          marketDate: published.market_date,
        };
        window.dispatchEvent(
          new CustomEvent(REFRESH_SETTLED_EVENT, { detail }),
        );
        clearDispatch();
        setDispatchedAt(null);
        setToast({ kind: "idle" });
      } catch {
        // Keep waiting within the bounded grace period. The existing snapshot
        // remains visible and no success state is fabricated.
      }
    };

    void pollPublish();
    const id = setInterval(() => void pollPublish(), 15_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [dispatchedAt]);

  const onClick = useCallback(async () => {
    setToast({ kind: "pending" });
    let dispatched = false;
    try {
      const r = await triggerRefresh("fast_intraday");
      if (r.ok) {
        const eta = r.eta_minutes ?? 18;
        const at = Date.now();
        setToast({ kind: "ok", min: eta });
        setEtaMin(eta);
        setDispatchedAt(at);
        saveDispatch(at, eta, r.dispatched_at, r.request_id);
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
  const inFlight = progress != null;
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
        <TmButton
          variant="secondary"
          size="sm"
          onClick={onClick}
          disabled={!isAdmin || pending || inFlight}
          title={!isAdmin ? (locale === "zh" ? "数据按计划更新，手动刷新仅限管理员" : "Data updates on schedule. Manual refresh requires the administrator.") : inFlight ? t(locale, "picks.refresh.inflight_tip") : undefined}
          loading={pending}
          loadingLabel={t(locale, "picks.refresh.pending")}
          className="rounded-[2px]"
        >
          {inFlight
            ? `${t(locale, "picks.refresh.inflight")} ${btnPct}%`
            : t(locale, "picks.refresh")}
        </TmButton>
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
