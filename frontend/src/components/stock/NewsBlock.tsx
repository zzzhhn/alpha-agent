"use client";

import { useEffect, useState } from "react";
import type { RatingCard, NewsItem, NewsRaw } from "@/lib/api/picks";
import { t, getLocaleFromStorage, type Locale, type TranslationKey } from "@/lib/i18n";

function decodeNewsRaw(raw: unknown): NewsItem[] {
  if (typeof raw !== "object" || raw === null) return [];
  const obj = raw as Partial<NewsRaw>;
  return obj.headlines ?? [];
}

function relativeTime(iso: string, locale: Locale): string {
  if (!iso) return locale === "zh" ? "未知" : "—";
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

const SENTIMENT_TONE: Record<NewsItem["sentiment"], string> = {
  pos: "bg-tm-pos",
  neg: "bg-tm-neg",
  neu: "bg-tm-muted",
};

const SENTIMENT_LABEL: Record<NewsItem["sentiment"], TranslationKey> = {
  pos: "news.sentiment_pos",
  neg: "news.sentiment_neg",
  neu: "news.sentiment_neu",
};

export default function NewsBlock({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);

  const news = card.breakdown.find((b) => b.signal === "news");
  const items = decodeNewsRaw(news?.raw);

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
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={`${item.link}-${i}`} className="flex gap-3 items-start">
            <span
              aria-label={t(locale, SENTIMENT_LABEL[item.sentiment])}
              className={`mt-1.5 inline-block w-2 h-2 rounded-full shrink-0 ${SENTIMENT_TONE[item.sentiment]}`}
            />
            <div className="flex-1 min-w-0">
              {item.link ? (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-tm-fg hover:text-tm-accent line-clamp-2"
                >
                  {item.title}
                </a>
              ) : (
                <div className="text-sm text-tm-fg line-clamp-2">{item.title}</div>
              )}
              <div className="text-xs text-tm-muted mt-1 flex gap-2">
                <span>{item.publisher || "—"}</span>
                <span>·</span>
                <span>{relativeTime(item.published_at, locale)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
