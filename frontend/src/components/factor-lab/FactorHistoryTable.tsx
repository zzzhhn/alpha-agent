"use client";

import { useState } from "react";
import { Clipboard, Check } from "lucide-react";
import clsx from "clsx";
import { useRouter } from "next/navigation";
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
import { TmButton, TmIconButton } from "@/components/tm/TmButton";
import {
  rollbackFactorProposal,
  type FactorProposal,
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

function StatusBadge({ status }: { status: string }) {
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
    <TmIconButton
      label="Copy expression"
      variant="ghost"
      size="xs"
      icon={
        copied ? (
          <Check className="h-3 w-3" strokeWidth={1.75} />
        ) : (
          <Clipboard className="h-3 w-3" strokeWidth={1.75} />
        )
      }
      onClick={handleCopy}
      title="Copy expression"
      className="ml-1"
    />
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
      <p className="px-3 py-4 text-center font-tm-mono text-xs text-tm-muted">
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
    <TmTableFrame>
      <TmTable density="compact" caption="Factor proposal history" className="min-w-[640px] text-xs">
        <TmTableHead>
          <TmTableRow>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              Expression
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              Status
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              dSharpe
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              Decided
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              By
            </TmTableHeaderCell>
            <TmTableHeaderCell textAlign="center" className="px-2 py-1.5 text-xs">
              Actions
            </TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {proposals.map((p) => {
            const isRowPending = pendingId === p.id;
            const rowError = rowErrors[p.id];
            const dsharpe =
              typeof p.evidence.deflated_sharpe === "number" &&
              !isNaN(p.evidence.deflated_sharpe)
                ? p.evidence.deflated_sharpe.toFixed(3)
                : "—";

            return (
              <TmTableRow key={p.id} className="align-top">
                {/* Expression */}
                <TmTableRowHeader className="max-w-[260px] px-2 py-1.5 font-normal">
                  <div className="flex items-start gap-1">
                    <code className="break-all font-mono text-xs text-tm-fg">
                      {p.expression}
                    </code>
                    <CopyButton text={p.expression} />
                  </div>
                </TmTableRowHeader>

                {/* Status */}
                <TmTableCell className="px-2 py-1.5">
                  <StatusBadge status={p.status} />
                </TmTableCell>

                {/* Deflated Sharpe */}
                <TmTableCell className="px-2 py-1.5 text-xs text-tm-fg-2">
                  {dsharpe}
                </TmTableCell>

                {/* Decided at */}
                <TmTableCell className="whitespace-nowrap px-2 py-1.5 text-xs text-tm-fg-2">
                  {relativeTime(p.decided_at)}
                </TmTableCell>

                {/* Decided by */}
                <TmTableCell className="px-2 py-1.5 text-xs text-tm-fg-2">
                  {p.decided_by ?? "—"}
                </TmTableCell>

                {/* Actions */}
                <TmTableCell textAlign="center" className="px-2 py-1.5">
                  {p.status === "approved" ? (
                    <div className="flex flex-col items-center gap-0.5">
                      <TmButton
                        variant="secondary"
                        size="xs"
                        disabled={isRowPending}
                        onClick={() => handleRollback(p.id)}
                        loading={isRowPending}
                        className="text-xs leading-[16px]"
                      >
                        Rollback
                      </TmButton>
                      {rowError && (
                        <p className="mt-0.5 max-w-[120px] text-center font-tm-mono text-xs text-tm-neg">
                          {rowError}
                        </p>
                      )}
                    </div>
                  ) : (
                    <span className="font-tm-mono text-xs text-tm-muted">
                      —
                    </span>
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
