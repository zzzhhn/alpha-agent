"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Square, AlertTriangle } from "lucide-react";
import { useSession } from "next-auth/react";
import { streamBrief } from "@/lib/api/streamBrief";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

type Status = "idle" | "streaming" | "done" | "error" | "aborted";
type Lang = "zh" | "en";

interface Sections {
  summary: string;
  bull: string;
  bear: string;
}

const EMPTY_SECTIONS: Sections = { summary: "", bull: "", bear: "" };

export default function RichThesis({ ticker }: { ticker: string }) {
  const { locale } = useLocale();
  const { status: authStatus } = useSession();
  const [status, setStatus] = useState<Status>("idle");
  const [sections, setSections] = useState<Sections>(EMPTY_SECTIONS);
  const [errMsg, setErrMsg] = useState<string>("");
  // Phase 312: brief language. Defaults to the page locale; user can flip
  // via the zh/en tab below the section header. Each language is a fresh
  // LLM call (token cost stays single-language; cheaper than asking the
  // model to emit both in one shot). cachedByLang keeps the prior language
  // visible so the user doesn't lose context while regenerating.
  const [briefLang, setBriefLang] = useState<Lang>(locale);
  const [cachedByLang, setCachedByLang] = useState<Record<Lang, Sections>>({
    zh: EMPTY_SECTIONS,
    en: EMPTY_SECTIONS,
  });
  const abortRef = useRef<AbortController | null>(null);

  // Keep briefLang in sync with the page locale on first render (avoids
  // a stale lang when the user lands on /stock from a Chinese Picks page).
  useEffect(() => {
    setBriefLang(locale);
  }, [locale]);

  // Defense-in-depth: even with key={ticker} on the parent (which already
  // unmounts this component on ticker change), guarantee any in-flight SSE
  // stream is aborted when ticker changes inside the same component instance.
  // Prevents orphan stream writes after a quick back-and-forth navigation
  // where React might reuse the fibre before the unmount path fires.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [ticker]);

  const onGenerate = useCallback(
    async (lang: Lang = briefLang) => {
      setStatus("streaming");
      setSections(EMPTY_SECTIONS);
      setErrMsg("");
      setBriefLang(lang);
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      try {
        let accumulated: Sections = { ...EMPTY_SECTIONS };
        for await (const ev of streamBrief(ticker, { language: lang }, ac.signal)) {
          if (ev.type === "done") {
            setStatus("done");
            // Cache the final per-language sections so flipping tabs back
            // shows the prior output instantly without re-streaming.
            setCachedByLang((prev) => ({ ...prev, [lang]: accumulated }));
            break;
          }
          if (ev.type === "error") {
            setErrMsg(ev.message);
            setStatus("error");
            break;
          }
          // Accumulate delta into the current section.
          accumulated = {
            ...accumulated,
            [ev.type]: accumulated[ev.type] + ev.delta,
          };
          setSections((prev) => ({
            ...prev,
            [ev.type]: prev[ev.type] + ev.delta,
          }));
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          setStatus("aborted");
        } else {
          setErrMsg(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    },
    [ticker, briefLang],
  );

  const onLangSwitch = useCallback(
    (next: Lang) => {
      if (next === briefLang) return;
      setBriefLang(next);
      const cached = cachedByLang[next];
      // If a prior session generated this language, restore immediately;
      // otherwise re-stream a fresh brief in the new language.
      if (cached.summary || cached.bull || cached.bear) {
        setSections(cached);
        setStatus("done");
      } else if (status === "done" || status === "error" || status === "aborted") {
        // Auto-regenerate when the user explicitly flips to a fresh
        // language after a completed brief. If still idle, wait for the
        // generate button click.
        onGenerate(next);
      } else {
        setSections(EMPTY_SECTIONS);
        setStatus("idle");
      }
    },
    [briefLang, cachedByLang, status, onGenerate],
  );

  const onAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const hasContent =
    sections.summary || sections.bull || sections.bear;

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-tm-fg flex items-center gap-2">
          <Sparkles aria-hidden className="w-4 h-4 text-tm-accent" strokeWidth={1.75} />
          {t(locale, "rich.title")}
        </h2>
        {authStatus === "authenticated" ? (
          <div className="flex items-center gap-2">
            {/* Phase 312 zh/en tab. Disabled during streaming to avoid a
                mid-stream abort + race; user can still abort via the Stop
                button and then switch language. */}
            <div className="inline-flex items-center rounded border border-tm-rule overflow-hidden text-xs font-tm-mono">
              <button
                type="button"
                onClick={() => onLangSwitch("zh")}
                disabled={status === "streaming"}
                className={
                  briefLang === "zh"
                    ? "bg-tm-accent text-tm-bg px-2 py-0.5"
                    : "bg-transparent text-tm-fg-2 hover:text-tm-fg px-2 py-0.5 disabled:opacity-40"
                }
                aria-pressed={briefLang === "zh"}
              >
                中文
              </button>
              <button
                type="button"
                onClick={() => onLangSwitch("en")}
                disabled={status === "streaming"}
                className={
                  briefLang === "en"
                    ? "bg-tm-accent text-tm-bg px-2 py-0.5"
                    : "bg-transparent text-tm-fg-2 hover:text-tm-fg px-2 py-0.5 disabled:opacity-40"
                }
                aria-pressed={briefLang === "en"}
              >
                EN
              </button>
            </div>
            {status === "streaming" ? (
              <button
                type="button"
                onClick={onAbort}
                className="inline-flex items-center gap-1 rounded border border-tm-rule px-2 py-1 text-xs text-tm-fg hover:border-tm-neg"
              >
                <Square aria-hidden className="w-3 h-3" strokeWidth={1.75} />
                {t(locale, "rich.stop_button")}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onGenerate(briefLang)}
                className="rounded border border-tm-rule bg-tm-bg px-3 py-1 text-xs text-tm-fg hover:border-tm-accent"
              >
                {hasContent
                  ? t(locale, "rich.regenerate_button")
                  : t(locale, "rich.generate_button")}
              </button>
            )}
          </div>
        ) : authStatus === "unauthenticated" ? (
          <Link
            href={`/signin?callbackUrl=/stock/${ticker}`}
            className="text-xs text-tm-accent hover:underline"
          >
            {t(locale, "rich.no_key_hint")}
          </Link>
        ) : null}
      </div>

      {status === "streaming" ? (
        <div className="text-xs text-tm-muted">{t(locale, "rich.streaming")}</div>
      ) : null}
      {status === "aborted" ? (
        <div className="text-xs text-tm-warn">{t(locale, "rich.aborted")}</div>
      ) : null}
      {status === "error" ? (
        <div className="text-xs text-tm-neg flex items-start gap-1">
          <AlertTriangle aria-hidden className="w-3 h-3 mt-0.5" strokeWidth={1.75} />
          <span>
            {t(locale, "rich.error_label")}
            {errMsg}
          </span>
        </div>
      ) : null}

      {hasContent ? (
        <div className="space-y-3 text-sm text-tm-fg-2">
          {sections.summary ? (
            <div>
              <div className="text-xs text-tm-muted uppercase tracking-wide mb-1">
                {t(locale, "rich.section_summary")}
              </div>
              <p className="whitespace-pre-wrap">{sections.summary}</p>
            </div>
          ) : null}
          {sections.bull ? (
            <div>
              <div className="text-xs text-tm-pos uppercase tracking-wide mb-1">
                {t(locale, "rich.section_bull")}
              </div>
              <p className="whitespace-pre-wrap">{sections.bull}</p>
            </div>
          ) : null}
          {sections.bear ? (
            <div>
              <div className="text-xs text-tm-neg uppercase tracking-wide mb-1">
                {t(locale, "rich.section_bear")}
              </div>
              <p className="whitespace-pre-wrap">{sections.bear}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
