"use client";

import { useMemo } from "react";
import { t, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { formatUtc8DateTime } from "@/lib/format-datetime";
import { HoverTip } from "@/components/ui/HoverTip";
import { formatWeightReason, pivotSignalWeights, type ObservatoryWeight } from "./observatory-model";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
  TmTableRowHeader,
} from "@/components/tm/TmTable";

export function WeightDeltaTable({
  weights,
  locale,
}: {
  weights: readonly ObservatoryWeight[];
  locale: Locale;
}) {
  const zh = locale === "zh";
  const rows = useMemo(() => pivotSignalWeights(weights), [weights]);

  if (rows.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-xs text-tm-muted text-center">
        {t(locale, "evolution.weights.empty")}
      </p>
    );
  }

  return (
    <TmTableFrame>
      <TmTable
        density="compact"
        caption={t(locale, "evolution.weights")}
        className="min-w-[640px] text-xs"
      >
        <TmTableHead>
          <TmTableRow>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.weights.col_signal")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{zh ? "线上 LIVE" : "LIVE"}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{zh ? "生效 EFFECTIVE" : "EFFECTIVE"}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{zh ? "影子 SHADOW" : "SHADOW"}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{zh ? "守护影子 GUARDED" : "GUARDED"}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="center" className="px-2 py-1.5">{t(locale, "evolution.weights.col_streak")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.weights.col_reason")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.weights.col_updated")}</TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {rows.map(({ signal_name, live, effective, shadow, guarded_shadow, latest }) => {
            const consecutiveBad = live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows ?? 0;
            const shadowStreak = shadow?.shadow_streak ?? 0;
            const reason = latest?.reason ?? null;
            const lastUpdated = latest?.last_updated ?? null;

            return (
              <TmTableRow
                key={signal_name}
              >
                {/* Signal */}
                <TmTableRowHeader className="px-2 py-1 font-tm-mono text-tm-fg">
                  <span className="inline-flex items-center gap-1.5">
                    {getSignalDisplayLabel(signal_name, locale)}
                    {consecutiveBad > 0 && (
                      <span className="inline-flex items-center rounded border border-tm-neg/40 bg-tm-neg/10 px-1 py-0 font-tm-mono text-xs text-tm-neg leading-4">
                        {t(locale, "evolution.weights.bad").replace(
                          "{n}",
                          String(consecutiveBad),
                        )}
                      </span>
                    )}
                  </span>
                </TmTableRowHeader>

                {[live, effective, shadow, guarded_shadow].map((weight, index) => (
                  <TmTableCell key={index} numeric textAlign="right" className="px-2 py-1 text-tm-fg">
                    {weight ? weight.weight.toFixed(4) : "—"}
                  </TmTableCell>
                ))}

                {/* Shadow streak toward promotion */}
                <TmTableCell numeric textAlign="center" className="px-2 py-1 text-tm-fg-2">
                  {shadow ? `${shadowStreak}/5` : "—"}
                </TmTableCell>

                {/* Reason */}
                <TmTableCell className="max-w-[200px] truncate px-2 py-1 text-tm-muted">
                  {reason ? <HoverTip content={reason}><span>{formatWeightReason(reason, locale)}</span></HoverTip> : "—"}
                </TmTableCell>

                {/* Last updated */}
                <TmTableCell className="px-2 py-1 text-tm-muted">
                  {formatTimestamp(lastUpdated)}
                </TmTableCell>
              </TmTableRow>
            );
          })}
        </TmTableBody>
      </TmTable>
    </TmTableFrame>
  );
}

function formatTimestamp(raw: string | null | undefined): string {
  return formatUtc8DateTime(raw);
}
