"use client";

import { useState } from "react";
import { ArrowRight } from "lucide-react";
import clsx from "clsx";
import {
  approveProposal,
  rejectProposal,
  type Proposal,
} from "@/lib/api/evolution";
import { useRouter } from "next/navigation";
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
  TmTableRowHeader,
} from "@/components/tm/TmTable";
import { TmButton } from "@/components/tm/TmButton";

// Localized status label. Falls back to the raw enum for any unmapped status.
function statusLabel(status: string, locale: Locale): string {
  const key = `evolution.proposals.status_${status}`;
  const translated = t(locale, key as Parameters<typeof t>[1]);
  return translated === key ? status : translated;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function formatNum(v: unknown, decimals = 4): string {
  if (typeof v !== "number" || isNaN(v)) return "—";
  return v.toFixed(decimals);
}

function formatChangedAt(raw: string): string {
  return formatUtc8DateTime(raw, { year: "two-digit", fallback: raw });
}

// ── Status badge ───────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  pending: {
    border: "border-tm-warn/40",
    bg: "bg-tm-warn/10",
    text: "text-tm-warn",
  },
  approved: {
    border: "border-tm-pos/40",
    bg: "bg-tm-pos/10",
    text: "text-tm-pos",
  },
  rejected: {
    border: "border-tm-neg/40",
    bg: "bg-tm-neg/10",
    text: "text-tm-neg",
  },
};

function StatusBadge({ status, locale }: { status: string; locale: Locale }) {
  const style = STATUS_STYLE[status] ?? {
    border: "border-tm-rule",
    bg: "bg-tm-bg-3/40",
    text: "text-tm-fg-2",
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
      {statusLabel(status, locale)}
    </span>
  );
}

// ── Evidence cell ──────────────────────────────────────────────────────────

function EvidenceCell({ evidence }: { evidence: Record<string, unknown> }) {
  const deflated =
    typeof evidence.deflated_sharpe === "number"
      ? formatNum(evidence.deflated_sharpe, 3)
      : null;
  const icOos =
    typeof evidence.ic_oos === "number"
      ? formatNum(evidence.ic_oos, 4)
      : null;
  const nTrials =
    typeof evidence.n_trials === "number"
      ? String(evidence.n_trials)
      : null;
  const rationale =
    typeof evidence.rationale === "string" ? evidence.rationale : null;

  const lines: string[] = [];
  if (deflated !== null) lines.push(`dSharpe=${deflated}`);
  if (icOos !== null) lines.push(`IC_OOS=${icOos}`);
  if (nTrials !== null) lines.push(`n_trials=${nTrials}`);

  return (
    <TmTableCell className="max-w-[260px] px-2 py-1 text-xs">
      {lines.length > 0 && (
        <div className="whitespace-nowrap text-tm-fg-2 mb-0.5">
          {lines.join(" · ")}
        </div>
      )}
      {rationale && (
        <div className="text-tm-muted leading-snug line-clamp-2">{rationale}</div>
      )}
      {lines.length === 0 && !rationale && (
        <span className="text-tm-muted">—</span>
      )}
    </TmTableCell>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function ProposalsTable({
  proposals,
  locale,
}: {
  proposals: Proposal[];
  locale: Locale;
}) {
  const router = useRouter();
  // Track which proposal id is currently awaiting a mutation (null = none)
  const [pendingId, setPendingId] = useState<number | null>(null);
  // Per-row error messages
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  if (proposals.length === 0) {
    return (
      <p className="px-3 py-4 font-tm-mono text-xs text-tm-muted text-center">
        {t(locale, "evolution.proposals.empty")}
      </p>
    );
  }

  async function handleAction(
    id: number,
    action: "approve" | "reject",
  ) {
    setPendingId(id);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    try {
      if (action === "approve") {
        await approveProposal(id);
      } else {
        await rejectProposal(id);
      }
      router.refresh();
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : t(locale, "evolution.proposals.request_failed");
      setRowErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <TmTableFrame>
      <TmTable
        density="compact"
        caption={t(locale, "evolution.proposals")}
        className="min-w-[620px] text-xs"
      >
        <TmTableHead>
          <TmTableRow>
            <TmTableHeaderCell textAlign="right" className="w-8 px-2 py-1.5 text-xs">#</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_field")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_change")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_evidence")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_status")}</TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_when")}</TmTableHeaderCell>
            <TmTableHeaderCell textAlign="center" className="px-2 py-1.5 text-xs">{t(locale, "evolution.proposals.col_actions")}</TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {proposals.map((p) => {
            const isRowPending = pendingId === p.id;
            const rowError = rowErrors[p.id];
            const isPending = p.status === "pending";

            return (
              <TmTableRow key={p.id} className="align-top">
                {/* ID */}
                <TmTableCell numeric textAlign="right" className="px-2 py-1.5 text-tm-muted">
                  {p.id}
                </TmTableCell>

                {/* Field */}
                <TmTableRowHeader className="whitespace-nowrap px-2 py-1.5 font-normal text-tm-fg">
                  {p.field}
                </TmTableRowHeader>

                {/* old -> new */}
                <TmTableCell className="whitespace-nowrap px-2 py-1.5 text-xs">
                  <span className="text-tm-neg">{formatValue(p.old_value)}</span>
                  <ArrowRight
                    className="inline mx-1 text-tm-muted"
                    size={10}
                    strokeWidth={1.75}
                  />
                  <span className="text-tm-pos">{formatValue(p.new_value)}</span>
                </TmTableCell>

                {/* Evidence */}
                <EvidenceCell evidence={p.evidence} />

                {/* Status */}
                <TmTableCell className="px-2 py-1.5">
                  <StatusBadge status={p.status} locale={locale} />
                </TmTableCell>

                {/* Timestamp */}
                <TmTableCell className="whitespace-nowrap px-2 py-1.5 text-xs">
                  {formatChangedAt(p.changed_at)}
                </TmTableCell>

                {/* Actions */}
                <TmTableCell textAlign="center" className="px-2 py-1.5">
                  {isPending ? (
                    <div className="flex items-center gap-1.5 justify-center">
                      <TmButton
                        variant="primary"
                        size="xs"
                        disabled={isRowPending}
                        onClick={() => handleAction(p.id, "approve")}
                        className="text-xs leading-[16px]"
                      >
                        {isRowPending ? "..." : t(locale, "evolution.proposals.approve")}
                      </TmButton>
                      <TmButton
                        variant="danger"
                        size="xs"
                        disabled={isRowPending}
                        onClick={() => handleAction(p.id, "reject")}
                        className="text-xs leading-[16px]"
                      >
                        {isRowPending ? "..." : t(locale, "evolution.proposals.reject")}
                      </TmButton>
                    </div>
                  ) : (
                    <span className="font-tm-mono text-xs text-tm-muted">
                      {statusLabel(p.status, locale)}
                    </span>
                  )}
                  {rowError && (
                    <p className="mt-0.5 font-tm-mono text-xs text-tm-neg text-center max-w-[120px]">
                      {rowError}
                    </p>
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
