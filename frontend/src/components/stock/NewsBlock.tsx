"use client";

import { useState } from "react";
import Link from "next/link";
import type { RatingCard, NewsItemLite } from "@/lib/api/picks";
import { enrichNewsForTicker } from "@/lib/api/news";
import { ApiException } from "@/lib/api/client";
import { t, type Locale } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

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

type EnrichState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; count: number }
  | { kind: "no_key" }
  | { kind: "error"; msg: string };

export default function NewsBlock({ card }: { card: RatingCard }) {
  const { locale } = useLocale();
  const [enrich, setEnrich] = useState<EnrichState>({ kind: "idle" });

  const items: NewsItemLite[] = card.news_items ?? [];
  const unenrichedCount = items.filter((it) => it.sentiment_label === null).length;

  const onEnrich = async () => {
    setEnrich({ kind: "loading" });
    try {
      const res = await enrichNewsForTicker(card.ticker);
      setEnrich({ kind: "done", count: res.enriched });
      // Page reload is the robust path: parent layout refetches the stock
      // card and any newly-enriched sentiment colours render. In-place
      // splice is a follow-up polish, not required for correctness.
      setTimeout(() => window.location.reload(), 1500);
    } catch (e) {
      if (e instanceof ApiException && e.status === 400) {
        setEnrich({ kind: "no_key" });
      } else {
        const msg = e instanceof Error ? e.message : "unknown";
        setEnrich({ kind: "error", msg });
      }
    }
  };

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
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-tm-fg">
          {t(locale, "news.title")}
        </h2>
        {unenrichedCount > 0 ? (
          <EnrichControl
            state={enrich}
            count={unenrichedCount}
            onClick={onEnrich}
            locale={locale}
          />
        ) : null}
      </div>
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

function EnrichControl({
  state,
  count,
  onClick,
  locale,
}: {
  state: EnrichState;
  count: number;
  onClick: () => void;
  locale: Locale;
}) {
  if (state.kind === "no_key") {
    return (
      <Link
        href="/settings"
        className="text-xs text-tm-muted underline hover:text-tm-accent"
      >
        {t(locale, "news.enrich_no_key_cta")}
      </Link>
    );
  }
  if (state.kind === "loading") {
    return (
      <span className="text-xs text-tm-muted">
        {t(locale, "news.enrich_loading")}
      </span>
    );
  }
  if (state.kind === "done") {
    return (
      <span className="text-xs text-tm-pos">
        {t(locale, "news.enrich_done").replace("{n}", String(state.count))}
      </span>
    );
  }
  if (state.kind === "error") {
    return (
      <button
        type="button"
        onClick={onClick}
        title={state.msg}
        className="text-xs text-tm-neg underline hover:opacity-80"
      >
        {t(locale, "news.enrich_error")}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded bg-tm-accent-soft px-2 py-1 text-xs text-tm-accent transition hover:bg-tm-accent hover:text-tm-bg"
    >
      {t(locale, "news.enrich_button")} ({count})
    </button>
  );
}
