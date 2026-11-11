"use client";

import { useEffect, useState } from "react";
import { fetchMacroContext, type MacroContextItem } from "@/lib/api/macro";
import { t, type Locale } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

function authorLabel(author: string | null, locale: Locale): string {
  if (author === "trump") return t(locale, "market_context.author_trump");
  if (author === "fed") return t(locale, "market_context.author_fed");
  if (author === "ofac") return t(locale, "market_context.author_ofac");
  return author ?? "";
}

function relativeTime(iso: string, locale: Locale): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return locale === "zh" ? `${mins} 分钟前` : `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return locale === "zh" ? `${hrs} 小时前` : `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return locale === "zh" ? `${days} 天前` : `${days}d ago`;
}

function toneClass(score: number | null): string {
  if (score === null) return "bg-tm-bg-3";
  if (score > 0.2) return "bg-tm-pos";
  if (score < -0.2) return "bg-tm-neg";
  return "bg-tm-muted";
}

export type MarketContextState =
  | { status: "loading" | "error" }
  | { status: "ready"; items: MacroContextItem[] };

export default function MarketContextWidget({ ticker }: { ticker: string }) {
  // Reset pending/results on navigation; a previous ticker must not leak in.
  return <MarketContextLoader key={ticker} ticker={ticker} />;
}

function MarketContextLoader({ ticker }: { ticker: string }) {
  const { locale } = useLocale();
  const [state, setState] = useState<MarketContextState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchMacroContext(ticker, 5)
      .then((r) => { if (!cancelled) setState({ status: "ready", items: r.items }); })
      .catch(() => { if (!cancelled) setState({ status: "error" }); });
    return () => { cancelled = true; };
  }, [ticker]);

  return <MarketContextContent state={state} locale={locale} />;
}

export function MarketContextContent({ state, locale }: { state: MarketContextState; locale: Locale }) {
  if (state.status !== "ready" || state.items.length === 0) {
    const message = state.status === "loading"
      ? (locale === "zh" ? "正在加载宏观事件…" : "Loading macro events…")
      : state.status === "error"
        ? (locale === "zh" ? "宏观事件暂时无法加载，请稍后重试。" : "Macro events could not be loaded. Please try again later.")
        : t(locale, "market_context.empty");
    return (
      <section aria-busy={state.status === "loading"} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-[2px] border border-tm-rule bg-tm-bg-2 px-3 py-2">
        <h2 className="text-sm font-semibold text-tm-fg">
          {t(locale, "market_context.title")}
        </h2>
        <p role="status" className={`text-xs ${state.status === "error" ? "text-tm-warn" : "text-tm-muted"}`}>{message}</p>
      </section>
    );
  }

  return (
    <section className="rounded-[2px] border border-tm-rule bg-tm-bg-2 p-4">
      <h2 className="text-lg font-semibold mb-3 text-tm-fg">
        {t(locale, "market_context.title")}
      </h2>
      <ul className="space-y-3">
        {state.items.map((it) => (
          <li key={it.id} className="flex gap-2 text-sm">
            <span className={`mt-1.5 inline-block h-2 w-2 rounded-full ${toneClass(it.sentiment_score)}`} />
            <div className="flex-1">
              <div className="text-tm-fg">
                <span className="mr-2 font-semibold text-tm-accent">
                  {authorLabel(it.author, locale)}
                </span>
                {it.url ? (
                  <a href={it.url} target="_blank" rel="noopener noreferrer"
                     className="hover:text-tm-accent">{it.title}</a>
                ) : (
                  <span>{it.title}</span>
                )}
              </div>
              {it.body_excerpt ? (
                <p className="mt-0.5 text-xs text-tm-muted">{it.body_excerpt}</p>
              ) : null}
              <div className="mt-1 flex flex-wrap gap-1 text-xs text-tm-muted">
                <span>{relativeTime(it.published_at, locale)}</span>
                {it.tickers_extracted.length > 0 ? (
                  <span>
                    {t(locale, "market_context.tickers_affected")}: {it.tickers_extracted.join(", ")}
                  </span>
                ) : null}
                {it.sectors_extracted.length > 0 ? (
                  <span>
                    {t(locale, "market_context.sectors_affected")}: {it.sectors_extracted.join(", ")}
                  </span>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
