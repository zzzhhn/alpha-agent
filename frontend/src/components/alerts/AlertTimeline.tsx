"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bell, Filter } from "lucide-react";
import { fetchAlertsRecent, type AlertRow } from "@/lib/api/alertsFeed";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";
import { useWatchlist } from "@/hooks/useWatchlist";
import WatchlistStar from "@/components/ui/WatchlistStar";

function relativeTime(iso: string, locale: Locale): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return locale === "zh" ? "刚刚" : "just now";
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

function fmtPayload(payload: AlertRow["payload"]): string {
  if (payload == null) return "—";
  if (typeof payload === "object" && !Array.isArray(payload)) {
    const entries = Object.entries(payload);
    if (entries.length === 0) return "—";
    return entries.map(([k, v]) => `${k}: ${String(v)}`).join(" · ");
  }
  return JSON.stringify(payload);
}

function typeLabel(t_: string, locale: Locale): string {
  const key = `alerts.type_${t_}` as Parameters<typeof t>[1];
  // Fall back to the raw type when no translation exists.
  const translated = t(locale, key);
  return translated === key ? t_ : translated;
}

export default function AlertTimeline({ ticker }: { ticker?: string }) {
  const [locale, setLocale] = useState<Locale>("zh");
  const [filter, setFilter] = useState<string>(ticker ?? "");
  const [rows, setRows] = useState<AlertRow[] | null>(null);
  const [err, setErr] = useState<string>("");
  const { isWatched } = useWatchlist();

  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await fetchAlertsRecent({
        ticker: filter.trim() || undefined,
        limit: 50,
      });
      setRows(r.alerts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRows([]);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Filter aria-hidden className="w-4 h-4 text-tm-muted" strokeWidth={1.75} />
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t(locale, "alerts.filter_placeholder")}
          className="rounded border border-tm-rule bg-tm-bg-2 px-2 py-1 text-sm text-tm-fg w-64"
        />
        <button
          type="button"
          onClick={load}
          className="text-xs text-tm-muted hover:text-tm-accent"
        >
          {locale === "zh" ? "刷新" : "Refresh"}
        </button>
      </div>

      {err ? (
        <div className="text-sm text-tm-neg">Error: {err}</div>
      ) : rows == null ? (
        <div className="text-sm text-tm-muted">{locale === "zh" ? "加载中…" : "Loading…"}</div>
      ) : rows.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-tm-muted">
          <Bell aria-hidden className="w-4 h-4" strokeWidth={1.75} />
          {t(locale, "alerts.empty")}
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-tm-fg-2 border-b border-tm-rule">
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_time")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_ticker")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_type")}</th>
              <th className="text-left px-2 py-1">{t(locale, "alerts.col_payload")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-tm-rule">
                <td className="px-2 py-1 text-tm-muted whitespace-nowrap">
                  {relativeTime(r.created_at, locale)}
                </td>
                <td className="px-2 py-1">
                  {isWatched(r.ticker) ? (
                    <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" />
                  ) : null}
                  <Link
                    href={`/stock/${r.ticker}`}
                    className={`font-mono hover:text-tm-accent ${isWatched(r.ticker) ? "text-tm-accent" : "text-tm-fg"}`}
                  >
                    {r.ticker}
                  </Link>
                </td>
                <td className="px-2 py-1 text-tm-fg-2">{typeLabel(r.type, locale)}</td>
                <td className="px-2 py-1 text-tm-muted font-mono">{fmtPayload(r.payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
