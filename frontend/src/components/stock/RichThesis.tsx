"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { Sparkles, Square, AlertTriangle } from "lucide-react";
import { useSession } from "next-auth/react";
import { streamBrief } from "@/lib/api/streamBrief";
import { t } from "@/lib/i18n";
import { useLocale } from "@/components/layout/LocaleProvider";

type Status = "idle" | "streaming" | "done" | "error" | "aborted";

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
  const abortRef = useRef<AbortController | null>(null);

  const onGenerate = useCallback(async () => {
    setStatus("streaming");
    setSections(EMPTY_SECTIONS);
    setErrMsg("");
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      for await (const ev of streamBrief(ticker, {}, ac.signal)) {
        if (ev.type === "done") {
          setStatus("done");
          break;
        }
        if (ev.type === "error") {
          setErrMsg(ev.message);
          setStatus("error");
          break;
        }
        // Accumulate delta into the current section.
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
  }, [ticker]);

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
                onClick={onGenerate}
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
