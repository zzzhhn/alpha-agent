"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Square } from "lucide-react";
import type { RatingCard, NewsItemLite } from "@/lib/api/picks";
import { streamNewsEnrich } from "@/lib/api/streamNewsEnrich";
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
  | { kind: "streaming" }
  | { kind: "done"; count: number }
  | { kind: "aborted" }
  | { kind: "no_key" }
  | { kind: "error"; msg: string };

export default function NewsBlock({ card }: { card: RatingCard }) {
  const { locale } = useLocale();
  const [enrich, setEnrich] = useState<EnrichState>({ kind: "idle" });
  // Local items state so enriched rows splice in place as each batch
  // streams back — no full-page reload. Seeded from the SSR card; reset
  // when the parent passes a new ticker's card.
  const [items, setItems] = useState<NewsItemLite[]>(card.news_items ?? []);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setItems(card.news_items ?? []);
    setEnrich({ kind: "idle" });
  }, [card.ticker, card.news_items]);

  // Defense-in-depth: abort any in-flight enrichment stream on unmount /
  // ticker change so orphan stream writes don't land on the next card.
  // Mirrors RichThesis.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [card.ticker]);

  const unenrichedCount = items.filter((it) => it.sentiment_label === null).length;

  const onEnrich = useCallback(async () => {
    setEnrich({ kind: "streaming" });
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    let enrichedCount = 0;
    try {
      // Pass the user's active locale so the LLM writes the reasoning
      // text in zh or en matching the UI; otherwise a 中文 user gets
      // English commentary by default.
      for await (const ev of streamNewsEnrich(card.ticker, locale, ac.signal)) {
        if (ev.type === "items") {
          enrichedCount += ev.items.length;
          // Splice each freshly-enriched row into the list in place by id.
          setItems((prev) => {
            const byId = new Map(ev.items.map((it) => [it.id, it]));
            return prev.map((it) => {
              const upd = byId.get(it.id);
              return upd
                ? {
                    ...it,
                    sentiment_score: upd.sentiment_score,
                    sentiment_label: upd.sentiment_label,
                    reasoning_text: upd.reasoning_text,
                    reasoning_lang: upd.reasoning_lang,
                  }
                : it;
            });
          });
        } else if (ev.type === "done") {
          setEnrich({ kind: "done", count: ev.enriched });
          break;
        } else if (ev.type === "error") {
          // A 400 means no BYOK key stored -> show the configure CTA,
          // matching the prior non-stream behaviour. Anything else is a
          // graceful inline error.
          if (ev.message.startsWith("HTTP 400")) {
            setEnrich({ kind: "no_key" });
          } else {
            setEnrich({ kind: "error", msg: ev.message });
          }
          break;
        }
        // "start" / "batch_failed" carry no UI state beyond progress.
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        setEnrich({ kind: "aborted" });
      } else {
        setEnrich({
          kind: "error",
          msg: e instanceof Error ? e.message : "unknown",
        });
      }
    }
    void enrichedCount;
  }, [card.ticker, locale]);

  const onAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  if (items.length === 0) {
    return (
      <section id="news" className="rounded border border-tm-rule bg-tm-bg-2 p-4">
        <h2 className="text-lg font-semibold mb-2 text-tm-fg">
          {t(locale, "news.title")}
        </h2>
        <p className="text-sm text-tm-muted">{t(locale, "news.empty")}</p>
      </section>
    );
  }

  return (
    <section id="news" className="rounded border border-tm-rule bg-tm-bg-2 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-tm-fg">
          {t(locale, "news.title")}
        </h2>
        {enrich.kind === "streaming" ? (
          <button
            type="button"
            onClick={onAbort}
            className="inline-flex items-center gap-1 rounded border border-tm-rule px-2 py-1 text-xs text-tm-fg hover:border-tm-neg"
          >
            <Square aria-hidden className="w-3 h-3" strokeWidth={1.75} />
            {t(locale, "rich.stop_button")}
          </button>
        ) : unenrichedCount > 0 ? (
          <EnrichControl
            state={enrich}
            count={unenrichedCount}
            onClick={onEnrich}
            locale={locale}
          />
        ) : enrich.kind !== "idle" ? (
          <EnrichControl
            state={enrich}
            count={unenrichedCount}
            onClick={onEnrich}
            locale={locale}
          />
        ) : null}
      </div>
      {enrich.kind === "streaming" ? (
        <p className="mb-2 text-xs text-tm-muted">
          {t(locale, "news.enrich_streaming")}
        </p>
      ) : null}
      {enrich.kind === "aborted" ? (
        <p className="mb-2 text-xs text-tm-warn">
          {t(locale, "news.enrich_aborted")}
        </p>
      ) : null}
      <ul className="space-y-3">
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
                <span className="rounded bg-tm-bg-3 px-1.5 py-0.5 font-tm-sans text-[11px]">
                  {it.source}
                </span>
                <span>{relativeTime(it.published_at, locale)}</span>
              </div>
              {it.reasoning_text ? (
                <p
                  lang={it.reasoning_lang ?? undefined}
                  className="mt-1 rounded border-l-2 border-tm-accent/40 bg-tm-bg-3/40 px-2 py-1 text-xs leading-relaxed text-tm-fg-2"
                >
                  {it.reasoning_text}
                </p>
              ) : null}
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
  // idle / aborted with remaining unenriched rows -> offer (re)trigger.
  if (count === 0) return null;
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
