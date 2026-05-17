"use client";

import { useEffect, useMemo, useState } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { deriveActionBox } from "@/lib/action-box";
import { t, getLocaleFromStorage, type Locale } from "@/lib/i18n";

export default function ActionBox({ card }: { card: RatingCard }) {
  const [locale, setLocale] = useState<Locale>("zh");
  useEffect(() => {
    setLocale(getLocaleFromStorage());
  }, []);
  const action = useMemo(() => {
    const tech = card.breakdown.find((b) => b.signal === "technicals")?.raw as
      | { atr?: number; current_price?: number }
      | undefined;
    const analyst = card.breakdown.find((b) => b.signal === "analyst")?.raw as
      | { target?: number; current?: number }
      | undefined;
    return deriveActionBox({
      currentPrice: tech?.current_price ?? analyst?.current ?? null,
      atr14: tech?.atr ?? null,
      analystTarget: analyst?.target ?? null,
      high180d: null,
      confidence:
        typeof card.confidence === "number" && isFinite(card.confidence)
          ? card.confidence
          : 0,
    });
  }, [card]);

  // Partial card (slow-only ticker): the entry/stop/target math needs the
  // `technicals` factor's ATR + live price, which only the intraday pipeline
  // produces. Show why instead of a box of placeholder dashes. useMemo above
  // still runs (hooks must be unconditional); its all-null result is unused.
  if (card.partial) {
    return (
      <div className="rounded border border-tm-rule-2 bg-tm-bg-2 p-3 text-sm">
        <div className="font-semibold text-tm-warn">{t(locale, "actionbox.title")}</div>
        <p className="mt-1.5 text-xs leading-relaxed text-tm-muted">
          {t(locale, "actionbox.partial_hint")}
        </p>
      </div>
    );
  }

  const dimmed = action.rrRatio !== null && action.rrRatio < 1.5;

  return (
    <div className={dimmed ? "opacity-50" : ""}>
      <div className="rounded border border-tm-rule-2 bg-tm-bg-2 p-3 space-y-1.5 text-sm">
        <div className="font-semibold text-tm-warn">{t(locale, "actionbox.title")}</div>
        {dimmed ? (
          <div className="text-xs text-tm-warn">
            ⚠ {t(locale, "actionbox.rr_warning")}
          </div>
        ) : null}
        <ActionRow
          label={t(locale, "actionbox.entry")}
          value={
            action.entryLow != null
              ? `${action.entryLow.toFixed(2)} - ${action.entryHigh!.toFixed(2)}`
              : "—"
          }
        />
        <ActionRow
          label={t(locale, "actionbox.stop")}
          value={action.stop != null ? action.stop.toFixed(2) : "—"}
        />
        <ActionRow
          label={t(locale, "actionbox.target")}
          value={action.target != null ? action.target.toFixed(2) : "—"}
        />
        <ActionRow
          label={t(locale, "actionbox.rr")}
          value={
            action.rrRatio != null ? `${action.rrRatio.toFixed(1)} : 1` : "—"
          }
        />
        <ActionRow
          label={t(locale, "actionbox.position")}
          value={`${action.positionPct?.toFixed(1) ?? "—"}%`}
        />
      </div>
    </div>
  );
}

function ActionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-tm-fg-2">{label}</span>
      <span className="font-mono text-tm-fg">{value}</span>
    </div>
  );
}
