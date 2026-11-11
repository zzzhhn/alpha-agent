"use client";
import { useAdminAccess } from "@/components/layout/SystemHealth";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmButton, TmIconButton } from "@/components/tm/TmButton";
import { GlossaryTip } from "@/components/zoo/GlossaryTip";
import { EvolutionUnavailable } from "@/components/evolution/EvolutionUnavailable";
import { TmDialog } from "@/components/tm/TmDialog";
import {
  approveFactorProposal,
  rejectFactorProposal,
  rejectFactorProposalsBatch,
  rollbackFactorProposal,
  type FactorProposal,
  type FactorProposalGroup,
} from "@/lib/api/factor-lab";

type RowActionState = "idle" | "approving" | "rejecting";

interface PendingProposalsSectionProps {
  readonly proposals: readonly FactorProposal[] | null;
  /** Server grouping by canonical expression; null falls back to one row per proposal. */
  readonly groups?: readonly FactorProposalGroup[] | null;
  readonly liveExpression: string;
}

/** One reviewable row: the latest proposal of a group plus its group metadata. */
export interface ProposalRow {
  readonly proposal: FactorProposal;
  readonly group: FactorProposalGroup | null;
}

export function proposalRows(
  proposals: readonly FactorProposal[],
  groups: readonly FactorProposalGroup[] | null | undefined,
): ProposalRow[] {
  if (!groups || groups.length === 0) return proposals.map((proposal) => ({ proposal, group: null }));
  const byId = new Map(proposals.map((proposal) => [proposal.id, proposal]));
  return groups.flatMap((group) => {
    const proposal = byId.get(group.latest_id);
    return proposal ? [{ proposal, group }] : [];
  });
}

function shortExpr(expr: string, max = 40): string {
  return expr.length <= max ? expr : expr.slice(0, max - 1) + "…";
}

function diffLines(
  live: string,
  next: string,
): readonly { sign: "-" | "+"; text: string }[] {
  return [
    { sign: "-" as const, text: live },
    { sign: "+" as const, text: next },
  ];
}

function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  return v.toFixed(decimals);
}

function meanOrNull(xs: readonly number[] | undefined): number | null {
  if (!xs || xs.length === 0) return null;
  const sum = xs.reduce((a, b) => a + b, 0);
  return sum / xs.length;
}

// Phase B2: skeptic risk badge colouring (low = clean, high = flagged).
const RISK_CLS: Record<string, string> = {
  low: "border-tm-pos text-tm-pos",
  medium: "border-tm-warn text-tm-warn",
  high: "border-tm-neg text-tm-neg",
};

export function PendingProposalsSection({
  proposals: loadedProposals,
  groups,
  liveExpression,
}: PendingProposalsSectionProps) {
  const { locale } = useLocale();
  const isAdmin = useAdminAccess();
  const { toast } = useToast();
  const router = useRouter();
  const proposals = loadedProposals ?? [];
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [actionState, setActionState] = useState<Map<number, RowActionState>>(
    new Map(),
  );

  const [confirmGroup, setConfirmGroup] = useState<FactorProposalGroup | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const rows = proposalRows(proposals, groups);

  const pageSize = 5;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  useEffect(() => setPage((value) => Math.min(value, pageCount - 1)), [pageCount]);
  const currentPage = Math.min(page, pageCount - 1);
  const visible = rows.slice(currentPage * pageSize, (currentPage + 1) * pageSize);

  async function handleRejectGroup(group: FactorProposalGroup) {
    setBatchBusy(true);
    try {
      const result = await rejectFactorProposalsBatch(group.proposal_ids);
      setConfirmGroup(null);
      router.refresh();
      toast.success(locale === "zh"
        ? `已拒绝 ${result.rejected} 条；记录保留，可在提案历史中查看`
        : `Rejected ${result.rejected}; records are kept in proposal history`);
    } catch {
      toast.error(t(locale, "factorLab.toast.rejectFailed"));
    } finally {
      setBatchBusy(false);
    }
  }

  function toggleExpand(id: number) {
    setExpandedId((current) => current === id ? null : id);
  }

  function setRowState(id: number, s: RowActionState) {
    setActionState((prev) => {
      const next = new Map(prev);
      if (s === "idle") next.delete(id);
      else next.set(id, s);
      return next;
    });
  }

  async function handleApprove(p: FactorProposal) {
    setRowState(p.id, "approving");
    try {
      await approveFactorProposal(p.id);
      router.refresh();
      toast.success(
        t(locale, "factorLab.toast.approved").replace(
          "{expression}",
          shortExpr(p.expression),
        ),
        {
          action: {
            label: t(locale, "factorLab.toast.undo"),
            onClick: () => {
              void (async () => {
                try {
                  await rollbackFactorProposal(p.id);
                  router.refresh();
                } catch {
                  toast.error(t(locale, "factorLab.toast.rollbackFailed"));
                }
              })();
            },
          },
          duration: 8000,
        },
      );
    } catch {
      toast.error(t(locale, "factorLab.toast.approveFailed"));
      router.refresh();
    } finally {
      setRowState(p.id, "idle");
    }
  }

  async function handleReject(p: FactorProposal) {
    setRowState(p.id, "rejecting");
    try {
      await rejectFactorProposal(p.id);
      router.refresh();
      toast.success(t(locale, "factorLab.toast.rejected"), {
        action: {
          label: t(locale, "factorLab.toast.undoRejected"),
          onClick: () => {
            void (async () => {
              try {
                await rollbackFactorProposal(p.id);
                router.refresh();
              } catch {
                toast.error(t(locale, "factorLab.toast.rollbackFailed"));
              }
            })();
          },
        },
        duration: 8000,
      });
    } catch {
      toast.error(t(locale, "factorLab.toast.rejectFailed"));
      router.refresh();
    } finally {
      setRowState(p.id, "idle");
    }
  }

  const title = locale === "zh" ? "方法论因子待审" : "Methodology factor proposals";

  if (loadedProposals === null) {
    return <TmPane title={title}><EvolutionUnavailable locale={locale} /></TmPane>;
  }

  if (proposals.length === 0) {
    return (
      <TmPane title={title} meta="0">
        <div className="px-3 py-2.5 font-tm-mono text-xs text-tm-muted">
          {t(locale, "factorLab.pending.empty")}
        </div>
      </TmPane>
    );
  }

  const zh = locale === "zh";
  return (
    <TmPane title={title} meta={groups ? (zh ? `${rows.length} 组 · ${proposals.length} 条` : `${rows.length} groups · ${proposals.length} rows`) : `${proposals.length}`}>
      {groups ? (
        <p className="border-b border-tm-rule px-3 py-2 text-xs leading-5 text-tm-muted">
          {zh
            ? "同一表达式的重复提案合并为一组。无验证数据的组来自旧版评估，数值全为 0，不代表因子有效。拒绝只改状态，不删除记录。"
            : "Repeated proposals of one expression are grouped. Groups without validation evidence come from the legacy evaluator (all zeros) and do not show a working factor. Rejecting changes status only; records are kept."}
        </p>
      ) : null}
      <div className="divide-y divide-tm-rule">
        {visible.map(({ proposal: p, group }) => {
          const isOpen = expandedId === p.id;
          const state = actionState.get(p.id) ?? "idle";
          // FactorProposal has `evidence` (not `metrics`); no hypothesis/justification.
          const ev = p.evidence;
          const ds = ev?.deflated_sharpe;
          const sharpeMean = meanOrNull(ev?.sharpes);
          const symptom = p.diagnostic?.symptom_summary;
          const rationale = ev?.llm_rationale;
          return (
            <div key={p.id} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <TmIconButton
                  label={locale === "zh" ? (isOpen ? `收起提案 #${p.id}` : `展开提案 #${p.id}`) : (isOpen ? `Collapse proposal #${p.id}` : `Expand proposal #${p.id}`)}
                  icon={
                    isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
                    )
                  }
                  size="xs"
                  variant="ghost"
                  onClick={() => toggleExpand(p.id)}
                  aria-expanded={isOpen}
                  className="shrink-0"
                />
                <code className="min-w-0 flex-1 truncate font-mono text-xs text-tm-fg" title={p.expression}>
                  {p.expression}
                </code>
                {ev?.skeptic ? (
                  <span
                    className={`shrink-0 border px-1.5 py-px font-tm-mono text-xs font-bold tracking-[0.04em] ${RISK_CLS[ev.skeptic.risk_level] ?? RISK_CLS.medium}`}
                    title={ev.skeptic.summary}
                  >
                    {(locale === "zh" ? "风险 " : "RISK ") +
                      ev.skeptic.risk_level.toUpperCase()}
                  </span>
                ) : null}
                {group && group.count > 1 ? (
                  <span className="shrink-0 border border-tm-rule px-1.5 py-px font-tm-mono text-xs text-tm-fg-2" title={zh ? `首次 ${group.first_created_at?.slice(0, 10) ?? "—"} · 最近 ${group.last_created_at?.slice(0, 10) ?? "—"}` : `First ${group.first_created_at?.slice(0, 10) ?? "—"} · latest ${group.last_created_at?.slice(0, 10) ?? "—"}`}>
                    {zh ? `重复 ${group.count} 次` : `${group.count}×`}
                  </span>
                ) : null}
                {group && !group.has_validation_evidence ? (
                  <span className="shrink-0 border border-tm-warn px-1.5 py-px font-tm-mono text-xs text-tm-warn">
                    {zh ? "无验证数据" : "No validation evidence"}
                  </span>
                ) : null}
                <span className="shrink-0 font-mono text-xs text-tm-fg-2">
                  <GlossaryTip term="DS">{t(locale, "factorLab.pending.colDS")}</GlossaryTip> {fmtNum(ds, 2)}
                </span>
                <TmButton
                  variant="secondary"
                  size="xs"
                  onClick={() => handleApprove(p)}
                  disabled={!isAdmin || state !== "idle"}
                  loading={state === "approving"}
                >
                  <span>{t(locale, "factorLab.pending.approve")}</span>
                </TmButton>
                <TmButton
                  variant="danger"
                  size="xs"
                  onClick={() => handleReject(p)}
                  disabled={!isAdmin || state !== "idle"}
                  loading={state === "rejecting"}
                >
                  <span>{t(locale, "factorLab.pending.reject")}</span>
                </TmButton>
                {group && group.count > 1 ? (
                  <TmButton
                    variant="secondary"
                    size="xs"
                    onClick={() => setConfirmGroup(group)}
                    disabled={!isAdmin || batchBusy}
                  >
                    <span>{zh ? `拒绝本组 ${group.count} 条` : `Reject all ${group.count}`}</span>
                  </TmButton>
                ) : null}
              </div>

              {isOpen ? (
                <div className="mt-2 ml-5 flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2.5">
                  {symptom ? (
                    <div>
                      <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.hypothesis")}
                      </div>
                      <p className="font-tm-mono text-xs text-tm-fg-2">
                        {symptom}
                      </p>
                    </div>
                  ) : null}
                  {rationale ? (
                    <div>
                      <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.justification")}
                      </div>
                      <p className="font-tm-mono text-xs text-tm-fg-2">
                        {rationale}
                      </p>
                    </div>
                  ) : null}
                  {ev ? (
                    <div>
                      <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.metrics")}
                      </div>
                      <div className="grid grid-cols-2 gap-2 font-mono text-xs text-tm-fg-2 sm:grid-cols-3">
                        <span>
                          dSharpe {fmtNum(ev.deflated_sharpe, 2)}
                        </span>
                        <span><GlossaryTip term="IC OOS">IC OOS</GlossaryTip> {fmtNum(ev.ic_oos, 4)}</span>
                        <span>Sharpe {fmtNum(sharpeMean, 2)}</span>
                        <span>
                          Baseline {fmtNum(ev.baseline_sharpe, 2)}
                        </span>
                        <span>
                          <GlossaryTip term="FOLDS">Folds</GlossaryTip> {ev.n_folds ?? "—"}
                        </span>
                        <span>
                          <GlossaryTip term="TRIALS">Trials</GlossaryTip> {ev.n_trials ?? "—"}
                        </span>
                        {typeof ev.self_correlation === "number" ? (
                          <span
                            title={
                              ev.self_correlation_with
                                ? `vs ${ev.self_correlation_with}`
                                : undefined
                            }
                          >
                            <GlossaryTip term="SELF-CORR">Self-corr</GlossaryTip> {fmtNum(ev.self_correlation, 2)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {ev?.skeptic ? (
                    <div>
                      <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
                        {(locale === "zh" ? "怀疑者审查 · " : "SKEPTIC · ") +
                          ev.skeptic.risk_level.toUpperCase()}
                      </div>
                      {ev.skeptic.summary ? (
                        <p className="font-tm-mono text-xs text-tm-fg-2">
                          {ev.skeptic.summary}
                        </p>
                      ) : null}
                      {ev.skeptic.concerns.length > 0 ? (
                        <ul className="mt-0.5 list-disc pl-4 font-tm-mono text-xs text-tm-fg-2">
                          {ev.skeptic.concerns.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                  <div>
                    <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
                      {t(locale, "factorLab.pending.diffVsLive")}
                    </div>
                    <pre className="overflow-x-auto rounded bg-tm-bg-3/60 p-2 font-mono text-xs">
                      {diffLines(liveExpression, p.expression).map(
                        (line, i) => (
                          <div
                            key={i}
                            className={
                              line.sign === "-"
                                ? "text-tm-neg"
                                : "text-tm-pos"
                            }
                          >
                            {line.sign} {line.text || (locale === "zh" ? "当前线上表达式不可用" : "Current live expression unavailable")}
                          </div>
                        ),
                      )}
                    </pre>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <TmDialog
        open={confirmGroup !== null}
        onClose={() => { if (!batchBusy) setConfirmGroup(null); }}
        title={zh ? "拒绝本组全部待审提案？" : "Reject every pending proposal in this group?"}
        closeLabel={zh ? "取消" : "Cancel"}
        className="max-w-[560px]"
      >
        {confirmGroup ? (
          <div className="space-y-3 text-sm leading-6 text-tm-fg-2">
            <code className="block break-all font-mono text-xs text-tm-fg">{confirmGroup.canonical_expression}</code>
            <p>
              {zh
                ? `将把 ${confirmGroup.count} 条仍待审的提案标为“已拒绝”。只改状态，不删除记录，也不改动线上因子。`
                : `Marks ${confirmGroup.count} still-pending proposals as rejected. Status only: nothing is deleted and the live factor is unchanged.`}
            </p>
            <div className="flex justify-end gap-2">
              <TmButton variant="secondary" size="sm" onClick={() => setConfirmGroup(null)} disabled={batchBusy}>
                {zh ? "取消" : "Cancel"}
              </TmButton>
              <TmButton variant="danger" size="sm" loading={batchBusy} onClick={() => void handleRejectGroup(confirmGroup)}>
                {zh ? `确认拒绝 ${confirmGroup.count} 条` : `Reject ${confirmGroup.count}`}
              </TmButton>
            </div>
          </div>
        ) : null}
      </TmDialog>
      <TmPagination
        page={currentPage + 1}
        pageSize={pageSize}
        totalItems={rows.length}
        pageSizeOptions={[pageSize]}
        labels={{
          navigation:
            locale === "zh"
              ? "待处理提案分页"
              : "Pending proposals pagination",
          previous: locale === "zh" ? "上一页" : "Prev",
          previousAriaLabel: locale === "zh" ? "上一页" : "Previous page",
          next: locale === "zh" ? "下一页" : "Next",
          nextAriaLabel: locale === "zh" ? "下一页" : "Next page",
          page: (currentPage, totalPages) =>
            locale === "zh"
              ? `第 ${currentPage}/${totalPages} 页`
              : `PAGE ${currentPage}/${totalPages}`,
          pageSize: locale === "zh" ? "每页" : "PAGE SIZE",
          total: (total) =>
            locale === "zh"
              ? `${groups ? "共" : "已加载"} ${total} ${groups ? "组" : "条"}`
              : `${total} ${groups ? "groups" : "loaded"}`,
        }}
        onPageChange={(nextPage) => {
          setPage(nextPage - 1);
          setExpandedId(null);
        }}
        onPageSizeChange={() => {
          setExpandedId(null);
        }}
      />
    </TmPane>
  );
}
