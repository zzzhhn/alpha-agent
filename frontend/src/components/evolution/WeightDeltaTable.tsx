"use client";

import { useMemo } from "react";
import clsx from "clsx";
import type { EvolutionWeight } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";
import { formatUtc8DateTime } from "@/lib/format-datetime";
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
  weights: EvolutionWeight[];
  locale: Locale;
}) {
  const rows = useMemo(() => {
    // Pivot flat list into one row per signal_name, joining live + shadow +
    // guarded_shadow (council #6 guarded-shrinkage candidate, not promoted).
    const map = new Map<
      string,
      {
        live: EvolutionWeight | null;
        shadow: EvolutionWeight | null;
        guarded: EvolutionWeight | null;
      }
    >();

    for (const w of weights) {
      const existing =
        map.get(w.signal_name) ?? { live: null, shadow: null, guarded: null };
      if (w.status === "live") {
        map.set(w.signal_name, { ...existing, live: w });
      } else if (w.status === "guarded_shadow") {
        map.set(w.signal_name, { ...existing, guarded: w });
      } else {
        map.set(w.signal_name, { ...existing, shadow: w });
      }
    }

    // Compute delta per signal, then sort by |delta| descending.
    const entries = Array.from(map.entries()).map(
      ([signal_name, { live, shadow, guarded }]) => {
        const liveWeight = live?.weight ?? null;
        const shadowWeight = shadow?.weight ?? null;
        const guardedWeight = guarded?.weight ?? null;
        const delta =
          liveWeight !== null && shadowWeight !== null
            ? shadowWeight - liveWeight
            : null;
        return {
          signal_name,
          live,
          shadow,
          liveWeight,
          shadowWeight,
          guardedWeight,
          delta,
        };
      },
    );

    entries.sort((a, b) => {
      const absDeltaA = a.delta !== null ? Math.abs(a.delta) : -1;
      const absDeltaB = b.delta !== null ? Math.abs(b.delta) : -1;
      return absDeltaB - absDeltaA;
    });

    return entries;
  }, [weights]);

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
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.weights.col_live")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.weights.col_shadow")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.weights.col_guarded")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.weights.col_delta")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="center" className="px-2 py-1.5">{t(locale, "evolution.weights.col_streak")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.weights.col_reason")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.weights.col_updated")}</TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {rows.map(({ signal_name, live, shadow, liveWeight, shadowWeight, guardedWeight, delta }) => {
            const consecutiveBad = live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows ?? 0;
            const shadowStreak = shadow?.shadow_streak ?? 0;
            const reason = shadow?.reason ?? live?.reason ?? null;
            const lastUpdated =
              shadow?.last_updated ?? live?.last_updated ?? null;

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

                {/* Live weight */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1 text-tm-fg">
                  {liveWeight !== null ? liveWeight.toFixed(4) : "—"}
                </TmTableCell>

                {/* Shadow weight (aggressive adaptive candidate) */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1 text-tm-fg-2">
                  {shadowWeight !== null ? shadowWeight.toFixed(4) : "—"}
                </TmTableCell>

                {/* Guarded-shrinkage shadow (council #6, not promoted live) */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1 text-tm-fg-2">
                  {guardedWeight !== null ? guardedWeight.toFixed(4) : "—"}
                </TmTableCell>

                {/* Delta */}
                <TmTableCell
                  numeric
                  textAlign="right"
                  className={clsx(
                    "px-2 py-1",
                    delta === null
                      ? "text-tm-muted"
                      : delta > 0
                        ? "text-tm-pos"
                        : delta < 0
                          ? "text-tm-neg"
                          : "text-tm-fg",
                  )}
                >
                  {delta === null
                    ? "—"
                    : `${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`}
                </TmTableCell>

                {/* Shadow streak toward promotion */}
                <TmTableCell numeric textAlign="center" className="px-2 py-1 text-tm-fg-2">
                  {shadow ? `${shadowStreak}/5` : "—"}
                </TmTableCell>

                {/* Reason */}
                <TmTableCell className="max-w-[200px] truncate px-2 py-1 text-tm-muted">
                  {reason ?? "—"}
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
