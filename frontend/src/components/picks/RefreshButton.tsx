"use client";
//
// Client-side "Refresh now" button + last-refresh badge for the picks page.
// Dispatches the cron-shards GH Actions workflow via /api/admin/refresh.
// The button is intentionally a soft trigger: the user sees "已派遣，约 18 分钟
// 后完成" toast and continues. The actual data shows up when they revisit
// or auto-refresh of the page itself (next manual reload).
import { useCallback, useEffect, useState } from "react";
import { triggerRefresh, fetchLastRefresh } from "@/lib/api/admin";
import { t, getLocaleFromStorage } from "@/lib/i18n";

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

export default function RefreshButton() {
  const [locale, setLocale] = useState<"zh" | "en">("zh");
  const [toast, setToast] = useState<ToastState>({ kind: "idle" });
  const [lastRun, setLastRun] = useState<string | null>(null);

  // Sync locale on mount (i18n stores in localStorage so SSR can't read it).
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  // Poll the lightweight /last_refresh endpoint on mount + every 60s so the
  // "X min ago" badge stays roughly current without page reload.
  useEffect(() => {
    let cancelled = false;
    const fetchAge = async () => {
      try {
        const r = await fetchLastRefresh();
        if (!cancelled) setLastRun(r.fast_intraday);
      } catch {
        // Silent — the badge just won't update; not worth surfacing.
      }
    };
    fetchAge();
    const id = setInterval(fetchAge, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const onClick = useCallback(async () => {
    setToast({ kind: "pending" });
    try {
      const r = await triggerRefresh("fast_intraday");
      if (r.ok) {
        setToast({ kind: "ok", min: r.eta_minutes ?? 18 });
        if (r.dispatched_at) setLastRun(r.dispatched_at);
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
    // Auto-clear non-pending toast after 6s
    setTimeout(() => setToast({ kind: "idle" }), 6000);
  }, []);

  const ageLabel = formatAge(lastRun, locale);
  const pending = toast.kind === "pending";
  const toastText = (() => {
    switch (toast.kind) {
      case "pending":
        return t(locale, "picks.refresh.pending");
      case "ok":
        return t(locale, "picks.refresh.dispatched").replace("{min}", String(toast.min));
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
    toast.kind === "ok"
      ? "text-tm-pos"
      : toast.kind === "failed" || toast.kind === "no_token"
        ? "text-tm-neg"
        : toast.kind === "cooldown"
          ? "text-tm-warn"
          : "text-tm-muted";

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-tm-muted">
        {t(locale, "picks.lastrun")}: <span className="text-tm-fg-2">{ageLabel}</span>
      </span>
      <button
        type="button"
        onClick={onClick}
        disabled={pending}
        className="rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 text-tm-fg hover:border-tm-accent disabled:cursor-not-allowed disabled:opacity-60"
      >
        {t(locale, pending ? "picks.refresh.pending" : "picks.refresh")}
      </button>
      {toastText ? (
        <span className={`text-xs ${toastTone}`}>{toastText}</span>
      ) : null}
    </div>
  );
}
