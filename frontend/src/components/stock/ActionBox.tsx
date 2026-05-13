"use client";

import { useMemo } from "react";
import type { RatingCard } from "@/lib/api/picks";
import { deriveActionBox } from "@/lib/action-box";

export default function ActionBox({ card }: { card: RatingCard }) {
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

  const dimmed = action.rrRatio !== null && action.rrRatio < 1.5;

  return (
    <div className={dimmed ? "opacity-50" : ""}>
      <div className="rounded border border-tm-rule-2 bg-tm-bg-2 p-3 space-y-1.5 text-sm">
        <div className="font-semibold text-tm-warn">Action</div>
        {dimmed ? (
          <div className="text-xs text-tm-warn">
            ⚠ R:R&lt;1.5 — wait for better entry
          </div>
        ) : null}
        <ActionRow
          label="Entry"
          value={
            action.entryLow != null
              ? `${action.entryLow.toFixed(2)} – ${action.entryHigh!.toFixed(2)}`
              : "—"
          }
        />
        <ActionRow
          label="Stop"
          value={action.stop != null ? action.stop.toFixed(2) : "—"}
        />
        <ActionRow
          label="Target"
          value={action.target != null ? action.target.toFixed(2) : "—"}
        />
        <ActionRow
          label="R:R"
          value={
            action.rrRatio != null ? `${action.rrRatio.toFixed(1)} : 1` : "—"
          }
        />
        <ActionRow
          label="Position"
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
