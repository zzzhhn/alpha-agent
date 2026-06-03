"use client";

/**
 * A1 (2026-05-19) Persona-as-prompt panel.
 *
 * Lets the user pick a named analyst persona (Technical / News /
 * Political / Options / Insider / Macro / Risk) and get a 2-3 sentence
 * LLM commentary scoped to that camp's signals. Critical: this is the
 * ONLY surface for persona LLM calls — the cron must never fan persona
 * requests per ticker per day (would 7x the BYOK token spend).
 *
 * Streaming (mirrors RichThesis): the commentary token-streams via SSE
 * (streamPersona). An AbortController in a ref backs the Stop button and
 * aborts any in-flight stream on unmount / ticker change. Each persona
 * response is still cached server-side via B3 per
 * (user, ticker, persona, language, as_of_date); a second click on the
 * same persona within 24h replays the cached text as one delta + done
 * (sub-100ms, zero LLM spend).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Lock, Square } from "lucide-react";

import { streamPersona } from "@/lib/api/streamPersona";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";
import { getPersonas } from "@/lib/personas";
import { useHasByok } from "@/hooks/useHasByok";

type Status = "idle" | "streaming" | "done" | "error" | "aborted";

export default function PersonaPanel({ ticker }: { ticker: string }) {
  const { locale } = useLocale();
  // Persona metadata is static config (7 entries, name+label+signals);
  // moved from a per-page GET /api/stock/personas fetch into a local
  // constant so the panel renders immediately without a network round
  // trip. LLM commentary stays click-gated through onExplain below.
  const personas = useMemo(() => getPersonas(locale), [locale]);
  // BYOK gate: persona commentary burns an LLM call, so show a lock + a
  // "configure key" link BEFORE the user clicks and hits an error.
  const { hasKey, loading: keyLoading } = useHasByok();
  const locked = !keyLoading && !hasKey;
  const [active, setActive] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [explanation, setExplanation] = useState("");
  const [cacheHit, setCacheHit] = useState(false);
  const [errMsg, setErrMsg] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  // Defense-in-depth: even with key={ticker} on the parent (which already
  // unmounts this component on ticker change), guarantee any in-flight SSE
  // stream is aborted when ticker changes inside the same component
  // instance. Mirrors RichThesis. Prevents orphan stream writes after a
  // quick back-and-forth navigation.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [ticker]);

  const onExplain = useCallback(
    async (name: string) => {
      setActive(name);
      setStatus("streaming");
      setExplanation("");
      setCacheHit(false);
      setErrMsg("");
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      try {
        for await (const ev of streamPersona(ticker, name, locale, ac.signal)) {
          if (ev.type === "done") {
            setCacheHit(ev.cache === "hit");
            setStatus("done");
            break;
          }
          if (ev.type === "error") {
            setErrMsg(ev.message);
            setStatus("error");
            break;
          }
          // Accumulate the explanation delta.
          setExplanation((prev) => prev + ev.delta);
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
    [ticker, locale],
  );

  const onAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  if (personas.length === 0) return null;

  const copy =
    locale === "zh"
      ? {
          title: "分析师视角",
          subtitle: "点击 persona 触发 LLM 解读 (BYOK + 24h 缓存)",
          loading: "生成中...",
          cacheHit: "(命中缓存)",
          tryAgain: "重试",
          lockedHint: "需要在 Settings 配置 LLM API Key 才能使用",
          configure: "去配置 →",
          aborted: "已取消",
        }
      : {
          title: "Analyst Personas",
          subtitle: "Click a persona to trigger LLM commentary (BYOK + 24h cache)",
          loading: "Generating...",
          cacheHit: "(cache hit)",
          tryAgain: "Try again",
          lockedHint: "Requires an LLM API key configured in Settings",
          configure: "Configure →",
          aborted: "Aborted",
        };

  return (
    <section className="rounded border border-tm-rule bg-tm-bg-2 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-tm-fg flex items-center gap-1.5">
            {copy.title}
            {locked ? <Lock aria-hidden className="h-3.5 w-3.5 text-tm-muted" strokeWidth={1.75} /> : null}
          </h2>
          <p className="mt-0.5 text-xs text-tm-muted">{copy.subtitle}</p>
        </div>
        {status === "streaming" ? (
          <button
            type="button"
            onClick={onAbort}
            className="inline-flex shrink-0 items-center gap-1 rounded border border-tm-rule px-2 py-1 text-xs text-tm-fg hover:border-tm-neg"
          >
            <Square aria-hidden className="w-3 h-3" strokeWidth={1.75} />
            {t(locale, "rich.stop_button")}
          </button>
        ) : null}
      </div>
      {locked ? (
        <div className="flex items-center gap-2 rounded border border-tm-rule bg-tm-bg-3/40 px-3 py-1.5 text-[11px] text-tm-muted">
          <Lock aria-hidden className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
          <span>{copy.lockedHint}</span>
          <Link href="/settings" className="text-tm-accent hover:underline">
            {copy.configure}
          </Link>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        {personas.map((p) => (
          <button
            key={p.name}
            type="button"
            onClick={() => void onExplain(p.name)}
            disabled={locked || status === "streaming"}
            className={`rounded border px-2.5 py-1 text-xs transition disabled:opacity-50 disabled:cursor-not-allowed ${
              active === p.name
                ? "border-tm-accent bg-tm-accent/15 text-tm-accent"
                : "border-tm-rule bg-tm-bg-3 text-tm-fg-2 hover:border-tm-accent/40 hover:text-tm-fg"
            }`}
            title={locked ? copy.lockedHint : p.signals.join(" + ")}
          >
            {status === "streaming" && active === p.name ? copy.loading : p.label}
          </button>
        ))}
      </div>
      {/* Live + completed output: render whatever has streamed so far so
          tokens paint as they arrive, not only on done. */}
      {explanation && (status === "streaming" || status === "done") ? (
        <div className="rounded border-l-2 border-tm-accent/40 bg-tm-bg-3/40 px-3 py-2 text-sm leading-relaxed text-tm-fg">
          <p className="whitespace-pre-wrap">{explanation}</p>
          {status === "done" && cacheHit ? (
            <p className="mt-1 text-[11px] text-tm-muted">{copy.cacheHit}</p>
          ) : null}
        </div>
      ) : null}
      {status === "aborted" ? (
        <div className="text-xs text-tm-warn">{copy.aborted}</div>
      ) : null}
      {status === "error" ? (
        <div className="flex items-center gap-2 text-xs text-tm-neg">
          <span>{errMsg}</span>
          <button
            type="button"
            onClick={() => active && void onExplain(active)}
            className="rounded border border-tm-neg/40 px-1.5 py-0.5"
          >
            {copy.tryAgain}
          </button>
        </div>
      ) : null}
    </section>
  );
}
