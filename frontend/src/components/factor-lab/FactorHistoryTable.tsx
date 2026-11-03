"use client";
import { useAdminAccess } from "@/components/layout/SystemHealth";

import { useState } from "react";
import { Clipboard, Check } from "lucide-react";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useLocale } from "@/components/layout/LocaleProvider";
import { EvolutionPagination } from "@/components/evolution/EvolutionPagination";
import { evolutionPage } from "@/components/evolution/review-state";
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

function StatusBadge({ status, zh }: { status: string; zh: boolean }) {
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
      {zh ? ({ pending: "待审", approved: "已批准", rejected: "已拒绝" } as Record<string, string>)[status] ?? status : status}
    </span>
  );
}

// ── Copy button ────────────────────────────────────────────────────────────

function CopyButton({ text, zh }: { text: string; zh: boolean }) {
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
      label={zh ? "复制表达式" : "Copy expression"}
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
      title={zh ? "复制表达式" : "Copy expression"}
      className="ml-1"
    />
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function FactorHistoryTable({
  proposals,
}: {
  proposals: readonly FactorProposal[];
}) {
  const router = useRouter();
  const isAdmin = useAdminAccess();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [requestedPage, setPage] = useState(1);
  const { page, visible } = evolutionPage(proposals, requestedPage);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});

  if (proposals.length === 0) {
    return (
      <p className="px-3 py-4 text-center font-tm-mono text-xs text-tm-muted">
        {zh ? "暂无历史记录。" : "No history yet."}
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
        e instanceof Error ? e.message : (zh ? "回滚失败，请重试。" : "Rollback failed. Please retry.");
      setRowErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <>
    <TmTableFrame>
      <TmTable density="compact" caption={zh ? "方法论提案历史" : "Methodology proposal history"} className="min-w-[640px] text-xs">
        <TmTableHead>
          <TmTableRow>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              {zh ? "表达式" : "Expression"}
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              {zh ? "状态" : "Status"}
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              dSharpe
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              {zh ? "处理时间" : "Decided"}
            </TmTableHeaderCell>
            <TmTableHeaderCell className="px-2 py-1.5 text-xs">
              {zh ? "处理人" : "By"}
            </TmTableHeaderCell>
            <TmTableHeaderCell textAlign="center" className="px-2 py-1.5 text-xs">
              {zh ? "操作" : "Actions"}
            </TmTableHeaderCell>
          </TmTableRow>
        </TmTableHead>
        <TmTableBody>
          {visible.map((p) => {
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
                    <CopyButton text={p.expression} zh={zh} />
                  </div>
                </TmTableRowHeader>

                {/* Status */}
                <TmTableCell className="px-2 py-1.5">
                  <StatusBadge status={p.status} zh={zh} />
                </TmTableCell>

                {/* Deflated Sharpe */}
                <TmTableCell className="px-2 py-1.5 text-xs text-tm-fg-2">
                  {dsharpe}
                </TmTableCell>

                {/* Decided at */}
                <TmTableCell className="whitespace-nowrap px-2 py-1.5 text-xs text-tm-fg-2">
                  {formatUtc8DateTime(p.decided_at, { year: "two-digit" })}
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
                        disabled={!isAdmin || isRowPending}
                        onClick={() => handleRollback(p.id)}
                        loading={isRowPending}
                        className="text-xs leading-[16px]"
                      >
                        {zh ? "回滚" : "Rollback"}
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
    <EvolutionPagination locale={locale} label={locale === "zh" ? "方法论提案历史分页" : "Methodology proposal history pagination"} page={page} total={proposals.length} onPageChange={setPage} />
    </>
  );
}
