"use client";

/**
 * B9 (2026-05-19) — diff card + 1-click rollback for settings.
 *
 * Renders the audit log of config edits from /api/user/settings/history
 * as a list of diff cards (mirrors AlertList.tsx visual pattern).
 * Rollback button on each card POSTs to /api/user/settings/rollback/{id}
 * and refreshes the list. Rollback is itself logged as a new row with
 * source='rollback' and rollback_of pointing back at the original.
 *
 * Source: synthesizer T9 + Douyin v#2 TraderCore "尺子不是修理工" —
 * every weight change must be visibly diff'd and reversible before
 * committing in the user's head.
 */

import { useCallback, useEffect, useState } from "react";

import { apiGet, apiPost } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";

interface ChangeRow {
  id: number;
  field: string;
  old_value: string | null;
  new_value: string | null;
  changed_at: string;
  source: string;
  rollback_of: number | null;
}

const ROLLBACK_SAFE_FIELDS = new Set([
  "byok.provider",
  "byok.model",
  "byok.base_url",
]);

function relTime(iso: string, locale: "zh" | "en"): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return locale === "zh" ? "刚刚" : "just now";
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

export default function ChangeLog() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<ChangeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [rolling, setRolling] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const r = await apiGet<{ changes: ChangeRow[] }>(
        "/api/user/settings/history?limit=50",
      );
      setRows(r.changes);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onRollback = useCallback(
    async (id: number) => {
      if (rolling !== null) return;
      setRolling(id);
      try {
        await apiPost(`/api/user/settings/rollback/${id}`, {} as Record<string, never>);
        await load();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setRolling(null);
      }
    },
    [load, rolling],
  );

  if (loading && rows.length === 0) {
    return (
      <div className="px-3 py-3 text-xs text-tm-muted">
        {locale === "zh" ? "加载中…" : "Loading…"}
      </div>
    );
  }
  if (err) {
    return (
      <div className="px-3 py-3 text-xs text-tm-neg">{err}</div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="px-3 py-3 text-xs text-tm-muted">
        {locale === "zh" ? "暂无设置变更记录" : "No setting changes yet"}
      </div>
    );
  }

  return (
    <ul className="divide-y divide-tm-rule">
      {rows.map((r) => {
        const isRolledBack = r.rollback_of !== null;
        const isRollbackSafe = ROLLBACK_SAFE_FIELDS.has(r.field);
        return (
          <li key={r.id} className="flex items-start gap-3 px-3 py-2 text-xs">
            <div className="flex-1 space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="font-tm-mono text-tm-fg">{r.field}</span>
                <span className="text-[10px] text-tm-muted">
                  {relTime(r.changed_at, locale)}
                </span>
                {r.source === "rollback" ? (
                  <span className="rounded bg-tm-warn/20 px-1.5 py-0 text-[10px] text-tm-warn">
                    ↶ {locale === "zh" ? "回滚" : "rollback"}
                    {r.rollback_of !== null ? ` #${r.rollback_of}` : null}
                  </span>
                ) : null}
              </div>
              <div className="font-tm-mono text-[11px]">
                <span className="text-tm-muted line-through">
                  {r.old_value ?? (locale === "zh" ? "(空)" : "(empty)")}
                </span>
                <span className="mx-2 text-tm-fg-2">→</span>
                <span className="text-tm-fg">
                  {r.new_value ?? (locale === "zh" ? "(空)" : "(empty)")}
                </span>
              </div>
            </div>
            {!isRolledBack && isRollbackSafe ? (
              <button
                type="button"
                onClick={() => void onRollback(r.id)}
                disabled={rolling === r.id}
                className="rounded border border-tm-rule px-2 py-0.5 text-[10px] text-tm-fg hover:border-tm-warn hover:text-tm-warn disabled:opacity-50"
              >
                {rolling === r.id
                  ? locale === "zh" ? "回滚中…" : "rolling back…"
                  : locale === "zh" ? "↶ 回滚" : "↶ rollback"}
              </button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
