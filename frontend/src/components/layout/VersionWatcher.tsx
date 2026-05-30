"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { t } from "@/lib/i18n";

// The commit SHA baked into THIS bundle at build time (next.config env). The
// live deploy's SHA comes from /api/fe/version at runtime; when they diverge,
// a newer version has shipped and we prompt a refresh.
const BAKED = process.env.NEXT_PUBLIC_BUILD_ID;
const POLL_MS = 60_000;
const COUNTDOWN_S = 30;

export default function VersionWatcher() {
  const { locale } = useLocale();
  const [newVersion, setNewVersion] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(COUNTDOWN_S);
  // Versions the user explicitly dismissed — don't re-prompt for the same one.
  const dismissedRef = useRef<string | null>(null);

  // Poll the live deploy version. Skip entirely when there's no real baked id
  // (local dev / "dev"), so localhost never shows the prompt.
  useEffect(() => {
    if (!BAKED || BAKED === "dev") return;

    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch("/api/fe/version", { cache: "no-store" });
        if (!r.ok) return;
        const data: { version?: string } = await r.json();
        const live = data.version;
        if (
          !cancelled &&
          live &&
          live !== "dev" &&
          live !== BAKED &&
          live !== dismissedRef.current
        ) {
          setNewVersion(live);
        }
      } catch {
        // Transient network/poll failure — ignore; next tick retries.
      }
    };

    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Drive the auto-refresh countdown once an update is detected.
  useEffect(() => {
    if (!newVersion) return;
    setCountdown(COUNTDOWN_S);
    const id = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          clearInterval(id);
          window.location.reload();
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [newVersion]);

  if (!newVersion) return null;

  const dismiss = () => {
    // Forgiveness: let the user defer the reload if mid-task. Remember this
    // version so the prompt doesn't immediately reappear on the next poll.
    dismissedRef.current = newVersion;
    setNewVersion(null);
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm">
      <div className="flex items-start gap-3 rounded-lg border border-tm-accent/50 bg-tm-bg-2 px-4 py-3 shadow-lg shadow-black/30">
        <RefreshCw
          className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-tm-accent [animation-duration:3s]"
          strokeWidth={1.75}
        />
        <div className="flex flex-col gap-2">
          <div className="font-tm-mono text-[12px] text-tm-fg">
            {t(locale, "version.new_available")}
          </div>
          <div className="font-tm-mono text-[11px] text-tm-muted">
            {t(locale, "version.auto_refresh").replace("{n}", String(countdown))}
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-1 rounded border border-tm-accent/60 bg-tm-accent px-2.5 py-1 font-tm-mono text-[11px] text-tm-bg transition-opacity hover:opacity-90"
            >
              {t(locale, "version.refresh_now")}
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="inline-flex items-center gap-1 rounded border border-tm-rule px-2.5 py-1 font-tm-mono text-[11px] text-tm-fg-2 transition-colors hover:bg-tm-bg-3/40"
            >
              {t(locale, "version.later")}
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label={t(locale, "version.later")}
          className="ml-1 shrink-0 text-tm-muted transition-colors hover:text-tm-fg"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}
