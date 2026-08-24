"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Filter } from "lucide-react";
import { fetchAlertsRecent, type AlertRow } from "@/lib/api/alertsFeed";
import { t, type Locale } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import WatchlistStar from "@/components/ui/WatchlistStar";
import { TmButton } from "@/components/tm/TmButton";
import { TmInput, TmSelect } from "@/components/tm/TmField";
import { TmStatePane } from "@/components/tm/TmStatePane";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";
import { TmTooltip } from "@/components/tm/TmTooltip";

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

// Same (ticker, type) alerts within this window collapse to one row + a
// count. The backend dedup_bucket can still emit adjacent buckets (e.g.
// 6h-ago + 7h-ago), which reads as spam; this folds clustered repeats while
// keeping genuinely separate events (a flare-up now vs days ago) distinct.
const DEDUP_WINDOW_MS = 60 * 60 * 1000;

interface DisplayRow extends AlertRow {
  count: number;
}

export default function AlertTimeline({ ticker }: { ticker?: string }) {
  const { locale } = useLocale();
  const [filter, setFilter] = useState<string>(ticker ?? "");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [rows, setRows] = useState<AlertRow[] | null>(null);
  const [err, setErr] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const { isWatched } = useWatchlist();

  const load = useCallback(async () => {
    setErr("");
    setLoading(true);
    try {
      const r = await fetchAlertsRecent({
        ticker: filter.trim() || undefined,
        limit: 50,
      });
      setRows(r.alerts);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  // Distinct alert types actually present (the type filter is client-side
  // over the loaded rows; the backend feed only filters by ticker). No
  // fabricated/stub types — the dropdown reflects what really exists.
  const availableTypes = useMemo(
    () => (rows ? Array.from(new Set(rows.map((r) => r.type))).sort() : []),
    [rows],
  );

  // Apply the client-side type filter, then collapse clustered duplicates.
  const displayRows = useMemo<DisplayRow[] | null>(() => {
    if (!rows) return null;
    const filtered = typeFilter
      ? rows.filter((r) => r.type === typeFilter)
      : rows;
    const sorted = [...filtered].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );
    const out: DisplayRow[] = [];
    for (const r of sorted) {
      // Fold into a more-recent kept alert of the same (ticker,type) if it
      // is within the dedup window. `out` is most-recent-first, so the
      // first match is the freshest kept representative.
      const rep = out.find(
        (o) =>
          o.ticker === r.ticker &&
          o.type === r.type &&
          new Date(o.created_at).getTime() - new Date(r.created_at).getTime() <=
            DEDUP_WINDOW_MS,
      );
      if (rep) rep.count += 1;
      else out.push({ ...r, count: 1 });
    }
    return out;
  }, [rows, typeFilter]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Filter aria-hidden className="w-4 h-4 text-tm-muted" strokeWidth={1.75} />
        <TmInput
          value={filter}
          onChange={setFilter}
          placeholder={t(locale, "alerts.filter_placeholder")}
          fieldSize="sm"
          className="w-64"
        />
        <TmSelect
          value={typeFilter}
          onChange={setTypeFilter}
          fieldSize="sm"
          options={[
            { value: "", label: t(locale, "alerts.filter_all_types") },
            ...availableTypes.map((value) => ({ value, label: typeLabel(value, locale) })),
          ]}
          aria-label={t(locale, "alerts.col_type")}
        />
        <TmButton
          variant="secondary"
          size="sm"
          onClick={load}
          loading={loading}
          loadingLabel={locale === "zh" ? "刷新中" : "Refreshing"}
        >
          {locale === "zh" ? "刷新" : "Refresh"}
        </TmButton>
      </div>

      {err ? (
        <TmStatePane
          state="error"
          title={locale === "zh" ? "警报加载失败" : "Alerts failed to load"}
          description={err}
          action={{
            label: locale === "zh" ? "重试" : "Retry",
            onClick: () => { void load(); },
            loading,
          }}
        />
      ) : displayRows == null ? (
        <TmStatePane
          state="loading"
          title={locale === "zh" ? "正在加载警报" : "Loading alerts"}
        />
      ) : displayRows.length === 0 ? (
        <TmStatePane
          state="empty"
          title={t(locale, "alerts.empty")}
          description={locale === "zh" ? "调整代码或类型筛选后重试。" : "Adjust the ticker or type filter and try again."}
        />
      ) : (
        <TmTableFrame>
          <TmTable density="compact" caption={locale === "zh" ? "最近警报" : "Recent alerts"}>
          <TmTableHead>
            <TmTableRow>
              <TmTableHeaderCell>{t(locale, "alerts.col_time")}</TmTableHeaderCell>
              <TmTableHeaderCell>{t(locale, "alerts.col_ticker")}</TmTableHeaderCell>
              <TmTableHeaderCell>{t(locale, "alerts.col_type")}</TmTableHeaderCell>
              <TmTableHeaderCell>{t(locale, "alerts.col_payload")}</TmTableHeaderCell>
            </TmTableRow>
          </TmTableHead>
          <TmTableBody>
            {displayRows.map((r) => (
              <TmTableRow key={r.id}>
                <TmTableCell className="whitespace-nowrap px-2 text-tm-muted">
                  {relativeTime(r.created_at, locale)}
                  {r.count > 1 ? (
                    <TmTooltip
                      content={t(locale, "alerts.dedup_hint")}
                      ariaLabel={t(locale, "alerts.dedup_hint")}
                    >
                      <span className="ml-1.5 rounded-[2px] bg-tm-bg-3 px-1 text-[10px] text-tm-fg-2">×{r.count}</span>
                    </TmTooltip>
                  ) : null}
                </TmTableCell>
                <TmTableRowHeader className="px-2 font-normal">
                  {isWatched(r.ticker) ? (
                    <WatchlistStar className="mr-1 inline-block h-2.5 w-2.5 align-middle text-tm-accent" />
                  ) : null}
                  {/* Deep-link to the stock detail's News section so the
                      alert is an action start, not a dead end. */}
                  <Link
                    href={`/stock/${r.ticker}#news`}
                    className={`font-mono hover:text-tm-accent ${isWatched(r.ticker) ? "text-tm-accent" : "text-tm-fg"}`}
                  >
                    {r.ticker}
                  </Link>
                </TmTableRowHeader>
                <TmTableCell className="px-2">{typeLabel(r.type, locale)}</TmTableCell>
                <TmTableCell className="px-2 text-tm-muted">{fmtPayload(r.payload)}</TmTableCell>
              </TmTableRow>
            ))}
          </TmTableBody>
          </TmTable>
        </TmTableFrame>
      )}
    </div>
  );
}
