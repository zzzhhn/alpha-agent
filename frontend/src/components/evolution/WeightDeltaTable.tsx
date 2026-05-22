"use client";

import { useMemo } from "react";
import clsx from "clsx";
import type { EvolutionWeight } from "@/lib/api/evolution";

export function WeightDeltaTable({ weights }: { weights: EvolutionWeight[] }) {
  const rows = useMemo(() => {
    // Pivot flat list into one row per signal_name, joining live + shadow.
    const map = new Map<
      string,
      { live: EvolutionWeight | null; shadow: EvolutionWeight | null }
    >();

    for (const w of weights) {
      const existing = map.get(w.signal_name) ?? { live: null, shadow: null };
      if (w.status === "live") {
        map.set(w.signal_name, { ...existing, live: w });
      } else {
        map.set(w.signal_name, { ...existing, shadow: w });
      }
    }

    // Compute delta per signal, then sort by |delta| descending.
    const entries = Array.from(map.entries()).map(([signal_name, { live, shadow }]) => {
      const liveWeight = live?.weight ?? null;
      const shadowWeight = shadow?.weight ?? null;
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
        delta,
      };
    });

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
        No weight data available.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-xs border-collapse">
        <thead>
          <tr className="text-tm-fg-2 border-b border-tm-rule">
            <th className="px-2 py-1.5 text-left">Signal</th>
            <th className="px-2 py-1.5 text-right">Live W</th>
            <th className="px-2 py-1.5 text-right">Shadow W</th>
            <th className="px-2 py-1.5 text-right">Delta</th>
            <th className="px-2 py-1.5 text-center">Streak</th>
            <th className="px-2 py-1.5 text-left">Reason</th>
            <th className="px-2 py-1.5 text-left">Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ signal_name, live, shadow, liveWeight, shadowWeight, delta }) => {
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
                    {signal_name}
                    {consecutiveBad > 0 && (
                      <span className="inline-flex items-center rounded border border-tm-neg/40 bg-tm-neg/10 px-1 py-0 font-tm-mono text-[9px] text-tm-neg leading-4">
                        bad&times;{consecutiveBad}
                      </span>
                    )}
                  </span>
                </td>

                {/* Live weight */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg">
                  {liveWeight !== null ? liveWeight.toFixed(4) : "—"}
                </td>

                {/* Shadow weight */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg-2">
                  {shadowWeight !== null ? shadowWeight.toFixed(4) : "—"}
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
