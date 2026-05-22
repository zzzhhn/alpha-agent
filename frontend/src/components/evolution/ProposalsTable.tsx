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

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] ?? {
    border: "border-tm-rule",
    bg: "bg-tm-bg-3/40",
    text: "text-tm-fg-2",
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
      {status}
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
    <td className="px-2 py-1 font-mono text-[10px] text-tm-fg-2 max-w-[260px]">
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
    </td>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function ProposalsTable({ proposals }: { proposals: Proposal[] }) {
  const router = useRouter();
  // Track which proposal id is currently awaiting a mutation (null = none)
  const [pendingId, setPendingId] = useState<number | null>(null);
  // Per-row error messages
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  if (proposals.length === 0) {
    return (
      <p className="px-3 py-4 font-tm-mono text-[11px] text-tm-muted text-center">
        No pending proposals. The proposer stays dormant until enough trading
        history accrues to validate a change.
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
        err instanceof Error ? err.message : "Request failed. Please retry.";
      setRowErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-xs border-collapse">
        <thead>
          <tr className="text-tm-fg-2 border-b border-tm-rule">
            <th className="px-2 py-1.5 text-right w-8 font-tm-mono text-[10px]">#</th>
            <th className="px-2 py-1.5 text-left font-tm-mono text-[10px]">Field</th>
            <th className="px-2 py-1.5 text-left font-tm-mono text-[10px]">Change</th>
            <th className="px-2 py-1.5 text-left font-tm-mono text-[10px]">Evidence</th>
            <th className="px-2 py-1.5 text-left font-tm-mono text-[10px]">Status</th>
            <th className="px-2 py-1.5 text-left font-tm-mono text-[10px]">When</th>
            <th className="px-2 py-1.5 text-center font-tm-mono text-[10px]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {proposals.map((p) => {
            const isRowPending = pendingId === p.id;
            const rowError = rowErrors[p.id];
            const isPending = p.status === "pending";

            return (
              <tr key={p.id} className="border-b border-tm-rule align-top">
                {/* ID */}
                <td className="px-2 py-1.5 text-right font-mono text-tm-muted">
                  {p.id}
                </td>

                {/* Field */}
                <td className="px-2 py-1.5 font-mono text-tm-fg whitespace-nowrap">
                  {p.field}
                </td>

                {/* old -> new */}
                <td className="px-2 py-1.5 font-mono text-[10px] whitespace-nowrap">
                  <span className="text-tm-neg">{formatValue(p.old_value)}</span>
                  <ArrowRight
                    className="inline mx-1 text-tm-muted"
                    size={10}
                    strokeWidth={1.75}
                  />
                  <span className="text-tm-pos">{formatValue(p.new_value)}</span>
                </td>

                {/* Evidence */}
                <EvidenceCell evidence={p.evidence} />

                {/* Status */}
                <td className="px-2 py-1.5">
                  <StatusBadge status={p.status} />
                </td>

                {/* Timestamp */}
                <td className="px-2 py-1.5 font-mono text-tm-fg-2 whitespace-nowrap text-[10px]">
                  {formatChangedAt(p.changed_at)}
                </td>

                {/* Actions */}
                <td className="px-2 py-1.5 text-center">
                  {isPending ? (
                    <div className="flex items-center gap-1.5 justify-center">
                      <button
                        disabled={isRowPending}
                        onClick={() => handleAction(p.id, "approve")}
                        className={clsx(
                          "inline-flex items-center rounded border px-2 py-0.5 font-tm-mono text-[9px] leading-[16px] transition-opacity",
                          "border-tm-pos/40 bg-tm-pos/10 text-tm-pos",
                          isRowPending
                            ? "opacity-40 cursor-not-allowed"
                            : "hover:bg-tm-pos/20",
                        )}
                      >
                        {isRowPending ? "..." : "approve"}
                      </button>
                      <button
                        disabled={isRowPending}
                        onClick={() => handleAction(p.id, "reject")}
                        className={clsx(
                          "inline-flex items-center rounded border px-2 py-0.5 font-tm-mono text-[9px] leading-[16px] transition-opacity",
                          "border-tm-neg/40 bg-tm-neg/10 text-tm-neg",
                          isRowPending
                            ? "opacity-40 cursor-not-allowed"
                            : "hover:bg-tm-neg/20",
                        )}
                      >
                        {isRowPending ? "..." : "reject"}
                      </button>
                    </div>
                  ) : (
                    <span className="font-tm-mono text-[9px] text-tm-muted">
                      {p.status}
                    </span>
                  )}
                  {rowError && (
                    <p className="mt-0.5 font-tm-mono text-[9px] text-tm-neg text-center max-w-[120px]">
                      {rowError}
                    </p>
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
