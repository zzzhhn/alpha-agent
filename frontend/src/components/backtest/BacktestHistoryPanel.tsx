"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import type { BacktestHistoryEntry } from "@/lib/types";

interface BacktestHistoryPanelProps {
  readonly favorites: readonly BacktestHistoryEntry[];
  readonly recent: readonly BacktestHistoryEntry[];
  readonly activeId: string | null;
  readonly onLoad: (entry: BacktestHistoryEntry) => void;
  readonly onToggleFavorite: (id: string) => void;
  readonly onRemove: (id: string) => void;
}

function formatTimeAgo(iso: string, locale: "zh" | "en"): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));
  const isZh = locale === "zh";
  if (diffSec < 60) return isZh ? "刚刚" : "just now";
  const min = Math.floor(diffSec / 60);
  if (min < 60) return isZh ? `${min} 分钟前` : `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return isZh ? `${h} 小时前` : `${h}h ago`;
  const d = Math.floor(h / 24);
  return isZh ? `${d} 天前` : `${d}d ago`;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function HistoryItem({
  entry,
  isActive,
  onLoad,
  onToggleFavorite,
  onRemove,
  locale,
}: {
  readonly entry: BacktestHistoryEntry;
  readonly isActive: boolean;
  readonly onLoad: (e: BacktestHistoryEntry) => void;
  readonly onToggleFavorite: (id: string) => void;
  readonly onRemove: (id: string) => void;
  readonly locale: "zh" | "en";
}) {
  const m = entry.result.metrics;
  const isProfit = m.total_return > 0;
  const sharpeColor =
    m.sharpe_ratio > 1 ? "text-green" : m.sharpe_ratio > 0 ? "text-yellow" : "text-red";

  return (
    <div
      className={`group relative rounded-md border px-2.5 py-2 text-xs transition-colors ${
        isActive
          ? "border-accent bg-accent/5"
          : "border-border bg-[var(--toggle-bg)] hover:border-accent/50"
      }`}
    >
      <button
        type="button"
        onClick={() => onLoad(entry)}
        className="block w-full text-left"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate font-mono text-[11px] font-semibold text-text">
            {entry.result.ticker}
          </span>
          <span className="shrink-0 text-[10px] text-muted">
            {formatTimeAgo(entry.timestamp, locale)}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-muted">
          <span>{entry.result.start_date}</span>
          <span>&rarr;</span>
          <span>{entry.result.end_date}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-3 text-[10px]">
          <span className={isProfit ? "text-green" : "text-red"}>
            {isProfit ? "+" : ""}
            {formatPct(m.total_return)}
          </span>
          <span className={sharpeColor}>
            SR {m.sharpe_ratio.toFixed(2)}
          </span>
          <span className="text-muted">
            {m.total_trades}
            {locale === "zh" ? " 笔" : " tr"}
          </span>
        </div>
      </button>

      <div className="absolute right-1.5 top-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite(entry.id);
          }}
          title={
            entry.isFavorite
              ? t(locale, "backtest.unfavorite")
              : t(locale, "backtest.favorite")
          }
          className="rounded p-0.5 text-muted hover:bg-border hover:text-text"
          aria-label="favorite"
        >
          {entry.isFavorite ? "\u2605" : "\u2606"}
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove(entry.id);
          }}
          title={t(locale, "backtest.removeEntry")}
          className="rounded p-0.5 text-muted hover:bg-border hover:text-red"
          aria-label="remove"
        >
          &times;
        </button>
      </div>

      {entry.isFavorite && (
        <span className="absolute left-1.5 top-1.5 text-[10px] text-accent">
          &#9733;
        </span>
      )}
    </div>
  );
}

export function BacktestHistoryPanel({
  favorites,
  recent,
  activeId,
  onLoad,
  onToggleFavorite,
  onRemove,
}: BacktestHistoryPanelProps) {
  const { locale } = useLocale();
  const hasAny = favorites.length > 0 || recent.length > 0;

  return (
    <Card>
      <CardHeader
        title={t(locale, "backtest.historyTitle")}
        icon="\uD83D\uDD52"
        subtitle={t(locale, "backtest.historySubtitle")}
      />
      <div className="space-y-3 p-3">
        {!hasAny && (
          <p className="px-1 text-[11px] leading-relaxed text-muted">
            {t(locale, "backtest.historyEmpty")}
          </p>
        )}

        {favorites.length > 0 && (
          <div className="space-y-1.5">
            <h4 className="px-1 text-[10px] font-semibold uppercase tracking-wider text-accent">
              {t(locale, "backtest.favorites")} ({favorites.length})
            </h4>
            {favorites.map((entry) => (
              <HistoryItem
                key={entry.id}
                entry={entry}
                isActive={entry.id === activeId}
                onLoad={onLoad}
                onToggleFavorite={onToggleFavorite}
                onRemove={onRemove}
                locale={locale}
              />
            ))}
          </div>
        )}

        {recent.length > 0 && (
          <div className="space-y-1.5">
            <h4 className="px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
              {t(locale, "backtest.recent")} ({recent.length})
            </h4>
            {recent.map((entry) => (
              <HistoryItem
                key={entry.id}
                entry={entry}
                isActive={entry.id === activeId}
                onLoad={onLoad}
                onToggleFavorite={onToggleFavorite}
                onRemove={onRemove}
                locale={locale}
              />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
