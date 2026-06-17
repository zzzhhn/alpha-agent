"use client";

import { useMemo } from "react";
import clsx from "clsx";
import type { EvolutionWeight } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";
import { getSignalDisplayLabel } from "@/lib/signal-labels";

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
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-muted text-center">
        {t(locale, "evolution.weights.empty")}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-xs border-collapse">
        <thead>
          <tr className="text-tm-fg-2 border-b border-tm-rule">
            <th className="px-2 py-1.5 text-left">{t(locale, "evolution.weights.col_signal")}</th>
            <th className="px-2 py-1.5 text-right">{t(locale, "evolution.weights.col_live")}</th>
            <th className="px-2 py-1.5 text-right">{t(locale, "evolution.weights.col_shadow")}</th>
            <th className="px-2 py-1.5 text-right">{t(locale, "evolution.weights.col_guarded")}</th>
            <th className="px-2 py-1.5 text-right">{t(locale, "evolution.weights.col_delta")}</th>
            <th className="px-2 py-1.5 text-center">{t(locale, "evolution.weights.col_streak")}</th>
            <th className="px-2 py-1.5 text-left">{t(locale, "evolution.weights.col_reason")}</th>
            <th className="px-2 py-1.5 text-left">{t(locale, "evolution.weights.col_updated")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ signal_name, live, shadow, liveWeight, shadowWeight, guardedWeight, delta }) => {
            const consecutiveBad = live?.consecutive_bad_windows ?? shadow?.consecutive_bad_windows ?? 0;
            const shadowStreak = shadow?.shadow_streak ?? 0;
            const reason = shadow?.reason ?? live?.reason ?? null;
            const lastUpdated =
              shadow?.last_updated ?? live?.last_updated ?? null;

            return (
              <tr
                key={signal_name}
                className="border-b border-tm-rule"
              >
                {/* Signal */}
                <td className="px-2 py-1 text-tm-fg font-tm-mono">
                  <span className="inline-flex items-center gap-1.5">
                    {getSignalDisplayLabel(signal_name, locale)}
                    {consecutiveBad > 0 && (
                      <span className="inline-flex items-center rounded border border-tm-neg/40 bg-tm-neg/10 px-1 py-0 font-tm-mono text-[9px] text-tm-neg leading-4">
                        {t(locale, "evolution.weights.bad").replace(
                          "{n}",
                          String(consecutiveBad),
                        )}
                      </span>
                    )}
                  </span>
                </td>

                {/* Live weight */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg">
                  {liveWeight !== null ? liveWeight.toFixed(4) : "—"}
                </td>

                {/* Shadow weight (aggressive adaptive candidate) */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg-2">
                  {shadowWeight !== null ? shadowWeight.toFixed(4) : "—"}
                </td>

                {/* Guarded-shrinkage shadow (council #6, not promoted live) */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg-2">
                  {guardedWeight !== null ? guardedWeight.toFixed(4) : "—"}
                </td>

                {/* Delta */}
                <td
                  className={clsx(
                    "px-2 py-1 text-right font-mono",
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
                </td>

                {/* Shadow streak toward promotion */}
                <td className="px-2 py-1 text-center font-mono text-tm-fg-2">
                  {shadow ? `${shadowStreak}/5` : "—"}
                </td>

                {/* Reason */}
                <td className="px-2 py-1 text-tm-muted max-w-[200px] truncate">
                  {reason ?? "—"}
                </td>

                {/* Last updated */}
                <td className="px-2 py-1 text-tm-muted">
                  {formatTimestamp(lastUpdated)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return "—";
  // Show date + time for weight updates (can span days)
  return d.toLocaleDateString([], { month: "2-digit", day: "2-digit" }) +
    " " +
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
