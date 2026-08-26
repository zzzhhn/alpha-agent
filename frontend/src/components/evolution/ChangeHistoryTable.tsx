"use client";

import clsx from "clsx";
import type { EvolutionChange } from "@/lib/api/evolution";
import { t, type Locale } from "@/lib/i18n";
import { formatUtc8DateTime } from "@/lib/format-datetime";
import {
  TmTable,
  TmTableBody,
  TmTableCell,
  TmTableFrame,
  TmTableHead,
  TmTableHeaderCell,
  TmTableRow,
} from "@/components/tm/TmTable";

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
  inversion_guard: {
    border: "border-tm-warn/40",
    bg: "bg-tm-warn/10",
    text: "text-tm-warn",
    label: "inversion_guard",
  },
};

// Retrospection cell: the affected signal's mean IC 7d before → 7d after the
// change. Green when the after side improved, red when it degraded — a record
// of what HAPPENED around the change, never a causal claim.
function IcAroundCell({ change }: { change: EvolutionChange }) {
  const b = change.ic_before;
  const a = change.ic_after;
  if (b == null && a == null) {
    return <span className="text-tm-muted">—</span>;
  }
  const fmt = (v: number | null | undefined) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
  const tone =
    b != null && a != null
      ? a > b
        ? "text-tm-pos"
        : a < b
          ? "text-tm-neg"
          : "text-tm-fg-2"
      : "text-tm-fg-2";
  return (
    <span className="font-mono tabular-nums">
      <span className="text-tm-muted">{fmt(b)}</span>
      <span className="mx-0.5 text-tm-muted">→</span>
      <span className={tone}>{fmt(a)}</span>
      {change.signal ? (
        <span className="ml-1 text-xs text-tm-muted">{change.signal}</span>
      ) : null}
    </span>
  );
}

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
        "inline-flex items-center rounded border px-1.5 py-0 font-tm-mono text-xs leading-[18px]",
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
  return formatUtc8DateTime(raw, { year: "two-digit", fallback: raw });
}

export function ChangeHistoryTable({
  changes,
  locale,
}: {
  changes: EvolutionChange[];
  locale: Locale;
}) {
  if (changes.length === 0) {
    return (
      <p className="px-1 py-4 font-tm-mono text-xs text-tm-muted text-center">
        {t(locale, "evolution.changes.empty")}
      </p>
    );
  }

  return (
    <TmTableFrame>
      <TmTable
        density="compact"
        caption={t(locale, "evolution.changes")}
        className="min-w-[480px] text-xs"
      >
        <TmTableHead>
          <TmTableRow>
            <TmTableHeaderCell textAlign="right" className="w-8 px-2 py-1.5">#</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.changes.col_time")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.changes.col_source")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.changes.col_baseline_ic")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="right" className="px-2 py-1.5">{t(locale, "evolution.changes.col_ic_around")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5">{t(locale, "evolution.changes.col_note")}</TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {changes.map((change) => {
            const baselineIc = parseBaselineIc(change.new_value);
            const isRollback = change.source === "auto_rollback";

            return (
              <TmTableRow key={change.id}>
                {/* ID */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1 text-tm-muted">
                  {change.id}
                </TmTableCell>

                {/* Timestamp */}
                <TmTableCell className="whitespace-nowrap px-2 py-1">
                  {formatChangedAt(change.changed_at)}
                </TmTableCell>

                {/* Source badge */}
                <TmTableCell className="px-2 py-1">
                  <SourceBadge source={change.source} />
                </TmTableCell>

                {/* Baseline IC */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1 text-tm-fg">
                  {baselineIc}
                </TmTableCell>

                {/* IC 7d before -> after (retrospection) */}
                <TmTableCell textAlign="right" className="px-2 py-1">
                  <IcAroundCell change={change} />
                </TmTableCell>

                {/* Note — rollback reference */}
                <TmTableCell className="px-2 py-1 text-tm-muted">
                  {isRollback && change.rollback_of !== null ? (
                    <span className="text-tm-neg">
                      &#x21A9;&nbsp;#{change.rollback_of}
                    </span>
                  ) : (
                    "—"
                  )}
                </TmTableCell>
              </TmTableRow>
            );
          })}
        </TmTableBody>
      </TmTable>
    </TmTableFrame>
  );
}
