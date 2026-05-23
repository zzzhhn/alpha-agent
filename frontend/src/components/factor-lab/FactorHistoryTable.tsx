"use client";

import { useState } from "react";
import { Clipboard, Check } from "lucide-react";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import {
  rollbackFactorProposal,
  type FactorProposal,
} from "@/lib/api/factor-lab";
import { StatusBadge } from "./PendingFactorProposalsTable";

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

// ── Relative time formatter ────────────────────────────────────────────────

function relativeTime(raw: string | null): string {
  if (!raw) return "—";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return raw;
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD}d ago`;
}

// ── Main component ─────────────────────────────────────────────────────────

export function FactorHistoryTable({
  proposals,
}: {
  proposals: FactorProposal[];
}) {
  const router = useRouter();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  if (proposals.length === 0) {
    return (
      <p className="px-3 py-4 text-center font-tm-mono text-[11px] text-tm-muted">
        No history yet.
      </p>
    );
  }

  async function handleRollback(id: number) {
    setPendingId(id);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });

    try {
      await rollbackFactorProposal(id);
      router.refresh();
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Rollback failed. Please retry.";
      setRowErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-xs">
        <thead>
          <tr className="border-b border-tm-rule text-left">
            <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
              Expression
            </th>
            <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
              Status
            </th>
            <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
              dSharpe
            </th>
            <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
              Decided
            </th>
            <th className="px-2 py-1.5 font-tm-mono text-[10px] text-tm-fg-2">
              By
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
            const dsharpe =
              typeof p.evidence.deflated_sharpe === "number" &&
              !isNaN(p.evidence.deflated_sharpe)
                ? p.evidence.deflated_sharpe.toFixed(3)
                : "—";

            return (
              <tr key={p.id} className="border-b border-tm-rule align-top">
                {/* Expression */}
                <td className="max-w-[260px] px-2 py-1.5">
                  <div className="flex items-start gap-1">
                    <code className="break-all font-mono text-[10px] text-tm-fg">
                      {p.expression}
                    </code>
                    <CopyButton text={p.expression} />
                  </div>
                </td>

                {/* Status */}
                <td className="px-2 py-1.5">
                  <StatusBadge status={p.status} />
                </td>

                {/* Deflated Sharpe */}
                <td className="px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                  {dsharpe}
                </td>

                {/* Decided at */}
                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                  {relativeTime(p.decided_at)}
                </td>

                {/* Decided by */}
                <td className="px-2 py-1.5 font-mono text-[10px] text-tm-fg-2">
                  {p.decided_by ?? "—"}
                </td>

                {/* Actions */}
                <td className="px-2 py-1.5 text-center">
                  {p.status === "approved" ? (
                    <div className="flex flex-col items-center gap-0.5">
                      <button
                        disabled={isRowPending}
                        onClick={() => handleRollback(p.id)}
                        className={clsx(
                          "inline-flex items-center rounded border px-2 py-0.5 font-tm-mono text-[9px] leading-[16px] transition-opacity",
                          "border-tm-rule bg-tm-bg-3/40 text-tm-fg-2",
                          isRowPending
                            ? "cursor-not-allowed opacity-40"
                            : "hover:bg-tm-bg-2 hover:text-tm-fg",
                        )}
                      >
                        {isRowPending ? "..." : "Rollback"}
                      </button>
                      {rowError && (
                        <p className="mt-0.5 max-w-[120px] text-center font-tm-mono text-[9px] text-tm-neg">
                          {rowError}
                        </p>
                      )}
                    </div>
                  ) : (
                    <span className="font-tm-mono text-[9px] text-tm-muted">
                      —
                    </span>
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
