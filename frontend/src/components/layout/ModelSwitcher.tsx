"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "./LocaleProvider";
import { t } from "@/lib/i18n";

interface LLMStatus {
  readonly provider: string;
  readonly model: string;
  readonly available: boolean;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:6008";

export function ModelSwitcher() {
  const { locale } = useLocale();
  const [status, setStatus] = useState<LLMStatus | null>(null);
  const [switching, setSwitching] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/llm/status`);
      if (res.ok) {
        setStatus(await res.json());
      }
    } catch {
      /* backend unreachable — keep last known state */
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const handleSwitch = async () => {
    if (!status || switching) return;
    const target = status.provider === "ollama" ? "openai" : "ollama";
    setSwitching(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/llm/switch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: target }),
      });
      if (res.ok) {
        // Switch returns {provider, model, message}; re-fetch full status
        await fetchStatus();
      }
    } catch {
      /* switch failed — keep current */
    } finally {
      setSwitching(false);
    }
  };

  const isGemma = status?.provider === "ollama";
  const displayName = status?.model ?? "...";
  const available = status?.available ?? false;

  return (
    <div className="mx-3 mb-2 rounded-lg border border-[var(--border)] bg-[var(--glass-bg)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
          {t(locale, "model.label")}
        </span>
        <span
          className={`h-1.5 w-1.5 rounded-full ${available ? "bg-[var(--green)]" : "bg-[var(--red)]"}`}
        />
      </div>

      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-medium text-[var(--text)]">
          {displayName}
        </span>
      </div>

      <button
        onClick={handleSwitch}
        disabled={switching}
        className="w-full rounded-md border border-[var(--border)] bg-[var(--card-inner)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--card)] hover:text-[var(--text)] disabled:opacity-50"
      >
        {switching
          ? t(locale, "model.switching")
          : t(locale, isGemma ? "model.switchToKimi" : "model.switchToGemma")}
      </button>
    </div>
  );
}
