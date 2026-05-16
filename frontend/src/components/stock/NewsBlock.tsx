"use client";

import { useEffect, useState } from "react";
import type { RatingCard, NewsItemLite } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

function relativeTime(iso: string, locale: Locale): string {
  if (!iso) return locale === "zh" ? "未知" : "n/a";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

const SENTIMENT_TONE: Record<NonNullable<NewsItemLite["sentiment_label"]>, string> = {
  pos: "bg-tm-pos",
  neg: "bg-tm-neg",
  neu: "bg-tm-muted",
};

export default function NewsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => { setLocale(getLocaleFromStorage()); }, []);

  const items: NewsItemLite[] = card.news_items ?? [];

  if (items.length === 0) {
    return (
      <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "news.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "news.empty")}</p>
      </section>
    );
  }

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "news.title")}
      </h2>
      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.id} className="flex gap-2 text-sm">
            {it.sentiment_label ? (
              <span className={`mt-1.5 inline-block h-2 w-2 rounded-full ${SENTIMENT_TONE[it.sentiment_label]}`} />
            ) : (
              <span className="mt-1.5 inline-block h-2 w-2 rounded-full bg-tm-bg-3" />
            )}
            <div className="flex-1">
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-tm-fg hover:text-tm-accent"
              >
                {it.headline}
              </a>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-tm-muted">
                <span className="rounded bg-tm-bg-3 px-1.5 py-0.5 font-tm-mono text-[10px]">
                  {it.source}
                </span>
                <span>{relativeTime(it.published_at, locale)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
