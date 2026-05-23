"use client";

import { useState } from "react";
import { Clipboard, Check } from "lucide-react";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import {
  approveFactorProposal,
  rejectFactorProposal,
  type FactorProposal,
  type ApproveResult,
} from "@/lib/api/factor-lab";

// ── Status badge ───────────────────────────────────────────────────────────

const STATUS_STYLE: Record<
  string,
  { border: string; bg: string; text: string }
> = {
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
    border: "border-tm-rule",
    bg: "bg-tm-bg-3/40",
    text: "text-tm-fg-2",
  },
};

export function StatusBadge({ status }: { status: string }) {
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

// ── Copy button ────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable; silently ignore
    }
  }

  return (
    <button
      onClick={handleCopy}
      title="Copy expression"
      className="ml-1 inline-flex items-center rounded p-0.5 text-tm-muted transition-colors hover:text-tm-fg"
    >
      {copied ? (
        <Check className="h-3 w-3" strokeWidth={1.75} />
      ) : (
        <Clipboard className="h-3 w-3" strokeWidth={1.75} />
      )}
    </button>
  );
}

// ── Number formatter ───────────────────────────────────────────────────────

function fmt(v: unknown, decimals = 3): string {
  if (typeof v !== "number" || isNaN(v)) return "—";
  return v.toFixed(decimals);
}

// ── Main component ─────────────────────────────────────────────────────────

export function PendingFactorProposalsTable({
  proposals,
}: {
  proposals: FactorProposal[];
}) {
  const router = useRouter();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [refreshError, setRefreshError] = useState<string | null>(null);

  if (proposals.length === 0) {
    return (
      <p className="px-3 py-4 text-center font-tm-mono text-[11px] text-tm-muted">
        No pending proposals. Click Propose above to generate candidates.
      </p>
    );
  }

  async function handleApprove(proposal: FactorProposal) {
    if (proposal.new_operators.length > 0) {
      const ok = window.confirm(
        "This proposal introduces new sandboxed operators. Approve?",
      );
      if (!ok) return;
    }

    setPendingId(proposal.id);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[proposal.id];
      return next;
    });

    try {
      const result: ApproveResult = await approveFactorProposal(proposal.id);
      if (result.refresh_error) {
        setRefreshError(result.refresh_error);
      }
      router.refresh();
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Approve failed. Please retry.";
      setRowErrors((prev) => ({ ...prev, [proposal.id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  async function handleReject(id: number) {
    setPendingId(id);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });

    try {
      await rejectFactorProposal(id);
      router.refresh();
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Reject failed. Please retry.";
      setRowErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {refreshError && (
        <div className="rounded border border-tm-warn/40 bg-tm-warn/10 px-3 py-2 font-tm-mono text-[10px] text-tm-warn">
          Post-approve refresh error: {refreshError}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-tm-rule text-left">
              <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
                Expression
              </th>
              <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
                dSharpe
              </th>
              <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
                IC OOS
              </th>
              <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
                Folds
              </th>
              <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
                New ops
              </th>
              <th className="px-2 py-1.5 text-center font-tm-mono text-[10px] text-tm-fg-2">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {proposals.map((p) => {
              const isRowPending = pendingId === p.id;
              const rowError = rowErrors[p.id];

              return (
                <tr
                  key={p.id}
                  className="border-b border-tm-rule align-top"
                >
                  {/* Expression */}
                  <td className="max-w-[260px] px-2 py-1.5">
                    <div className="flex items-start gap-1">
                      <code className="break-all font-mono text-[10px] text-tm-fg">
                        {p.expression}
                      </code>
                      <CopyButton text={p.expression} />
                    </div>
                  </td>

                  {/* Deflated Sharpe */}
                  <td className="px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                    {fmt(p.evidence.deflated_sharpe, 3)}
                  </td>

                  {/* IC OOS */}
                  <td className="px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                    {fmt(p.evidence.ic_oos, 4)}
                  </td>

                  {/* n_folds */}
                  <td className="px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                    {p.evidence.n_folds}
                  </td>

                  {/* New operators */}
                  <td className="max-w-[200px] px-2 py-1.5">
                    {p.new_operators.length === 0 ? (
                      <span className="font-tm-mono text-[10px] text-tm-muted">
                        none
                      </span>
                    ) : (
                      <details>
                        <summary className="cursor-pointer font-tm-mono text-[10px] text-tm-warn">
                          {p.new_operators.length} new op
                          {p.new_operators.length !== 1 ? "s" : ""}
                        </summary>
                        <div className="mt-1 flex flex-col gap-1.5">
                          {p.new_operators.map((op) => (
                            <div key={op.name}>
                              <div className="font-tm-mono text-[9px] text-tm-fg">
                                {op.name}{" "}
                                <span className="text-tm-muted">
                                  {op.signature}
                                </span>
                              </div>
                              <pre className="overflow-x-auto rounded bg-tm-bg-2 p-2 font-mono text-[9px] text-tm-fg-2">
                                {op.python_impl}
                              </pre>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="px-2 py-1.5 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <button
                        disabled={isRowPending}
                        onClick={() => handleApprove(p)}
                        className={clsx(
                          "inline-flex items-center rounded border px-2 py-0.5 font-tm-mono text-[9px] leading-[16px] transition-opacity",
                          "border-tm-pos/40 bg-tm-pos/10 text-tm-pos",
                          isRowPending
                            ? "cursor-not-allowed opacity-40"
                            : "hover:bg-tm-pos/20",
                        )}
                      >
                        {isRowPending ? "..." : "Approve"}
                      </button>
                      <button
                        disabled={isRowPending}
                        onClick={() => handleReject(p.id)}
                        className={clsx(
                          "inline-flex items-center rounded border px-2 py-0.5 font-tm-mono text-[9px] leading-[16px] transition-opacity",
                          "border-tm-neg/40 bg-tm-neg/10 text-tm-neg",
                          isRowPending
                            ? "cursor-not-allowed opacity-40"
                            : "hover:bg-tm-neg/20",
                        )}
                      >
                        {isRowPending ? "..." : "Reject"}
                      </button>
                    </div>
                    {rowError && (
                      <p className="mt-0.5 max-w-[140px] text-center font-tm-mono text-[9px] text-tm-neg">
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
    </div>
  );
}
