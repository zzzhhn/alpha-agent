"use client";

import clsx from "clsx";
import type { EvolutionChange } from "@/lib/api/evolution";

// Source badge color mapping
const SOURCE_BADGE: Record<
  string,
  { border: string; bg: string; text: string; label: string }
> = {
  auto_promote: {
    border: "border-tm-pos/40",
    bg: "bg-tm-pos/10",
    text: "text-tm-pos",
    label: "auto_promote",
  },
  auto_rollback: {
    border: "border-tm-neg/40",
    bg: "bg-tm-neg/10",
    text: "text-tm-neg",
    label: "auto_rollback",
  },
  cold_start_seed: {
    border: "border-tm-rule",
    bg: "bg-tm-bg-3/40",
    text: "text-tm-muted",
    label: "cold_start_seed",
  },
};

function SourceBadge({ source }: { source: string }) {
  const style = SOURCE_BADGE[source] ?? {
    border: "border-tm-rule",
    bg: "bg-tm-bg-3/40",
    text: "text-tm-fg-2",
    label: source,
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded border px-1.5 py-0 font-tm-mono text-[9px] leading-[18px]",
        style.border,
        style.bg,
        style.text,
      )}
    >
      {style.label}
    </span>
  );
}

function parseBaselineIc(newValue: string): string {
  try {
    const parsed: unknown = JSON.parse(newValue);
    if (
      parsed !== null &&
      typeof parsed === "object" &&
      "baseline_ic" in parsed &&
      typeof (parsed as Record<string, unknown>).baseline_ic === "number"
    ) {
      const ic = (parsed as Record<string, unknown>).baseline_ic as number;
      return `${ic >= 0 ? "+" : ""}${ic.toFixed(4)}`;
    }
  } catch {
    // malformed JSON — fall through
  }
  return "—";
}

function formatChangedAt(raw: string): string {
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  return (
    d.toLocaleDateString([], {
      month: "2-digit",
      day: "2-digit",
      year: "2-digit",
    }) +
    " " +
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  );
}

export function ChangeHistoryTable({ changes }: { changes: EvolutionChange[] }) {
  if (changes.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-[10.5px] text-tm-muted text-center">
        No weight changes recorded yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-xs border-collapse">
        <thead>
          <tr className="text-tm-fg-2 border-b border-tm-rule">
            <th className="px-2 py-1.5 text-right w-8">#</th>
            <th className="px-2 py-1.5 text-left">Timestamp</th>
            <th className="px-2 py-1.5 text-left">Source</th>
            <th className="px-2 py-1.5 text-right">Baseline IC</th>
            <th className="px-2 py-1.5 text-left">Note</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change) => {
            const baselineIc = parseBaselineIc(change.new_value);
            const isRollback = change.source === "auto_rollback";

            return (
              <tr key={change.id} className="border-b border-tm-rule">
                {/* ID */}
                <td className="px-2 py-1 text-right font-mono text-tm-muted">
                  {change.id}
                </td>

                {/* Timestamp */}
                <td className="px-2 py-1 font-mono text-tm-fg-2 whitespace-nowrap">
                  {formatChangedAt(change.changed_at)}
                </td>

                {/* Source badge */}
                <td className="px-2 py-1">
                  <SourceBadge source={change.source} />
                </td>

                {/* Baseline IC */}
                <td className="px-2 py-1 text-right font-mono text-tm-fg">
                  {baselineIc}
                </td>

                {/* Note — rollback reference */}
                <td className="px-2 py-1 font-mono text-tm-muted">
                  {isRollback && change.rollback_of !== null ? (
                    <span className="text-tm-neg">
                      &#x21A9;&nbsp;#{change.rollback_of}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
