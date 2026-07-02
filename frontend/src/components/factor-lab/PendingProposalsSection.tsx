"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useToast } from "@/components/ui/toast";
import { t } from "@/lib/i18n";
import { TmPane } from "@/components/tm/TmPane";
import {
  approveFactorProposal,
  rejectFactorProposal,
  rollbackFactorProposal,
  type FactorProposal,
} from "@/lib/api/factor-lab";

type RowActionState = "idle" | "approving" | "rejecting";

interface PendingProposalsSectionProps {
  readonly proposals: readonly FactorProposal[];
  readonly liveExpression: string;
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
  proposals,
  liveExpression,
}: PendingProposalsSectionProps) {
  const { locale } = useLocale();
  const { toast } = useToast();
  const router = useRouter();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [actionState, setActionState] = useState<Map<number, RowActionState>>(
    new Map(),
  );

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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

  const title = t(locale, "factorLab.pending.title");

  if (proposals.length === 0) {
    return (
      <TmPane title={title} meta="0">
        <div className="px-3 py-2.5 font-tm-mono text-[11px] text-tm-muted">
          {t(locale, "factorLab.pending.empty")}
        </div>
      </TmPane>
    );
  }

  return (
    <TmPane title={title} meta={`${proposals.length}`}>
      <div className="divide-y divide-tm-rule">
        {proposals.map((p) => {
          const isOpen = expanded.has(p.id);
          const state = actionState.get(p.id) ?? "idle";
          // FactorProposal has `evidence` (not `metrics`); no hypothesis/justification.
          const ev = p.evidence;
          const ds = ev?.deflated_sharpe;
          const sharpeMean = meanOrNull(ev?.sharpes);
          const symptom = p.diagnostic?.symptom_summary;
          const rationale = ev?.llm_rationale;
          return (
            <div key={p.id} className="px-3 py-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleExpand(p.id)}
                  className="text-tm-muted hover:text-tm-fg"
                  aria-expanded={isOpen}
                  aria-label="expand"
                >
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.75} />
                  )}
                </button>
                <code className="flex-1 truncate font-mono text-[11px] text-tm-fg">
                  {p.expression}
                </code>
                {ev?.skeptic ? (
                  <span
                    className={`shrink-0 border px-1.5 py-px font-tm-mono text-[9px] font-bold tracking-[0.04em] ${RISK_CLS[ev.skeptic.risk_level] ?? RISK_CLS.medium}`}
                    title={ev.skeptic.summary}
                  >
                    {(locale === "zh" ? "风险 " : "RISK ") +
                      ev.skeptic.risk_level.toUpperCase()}
                  </span>
                ) : null}
                <span className="shrink-0 font-mono text-[11px] text-tm-fg-2">
                  {t(locale, "factorLab.pending.colDS")} {fmtNum(ds, 2)}
                </span>
                <button
                  type="button"
                  onClick={() => handleApprove(p)}
                  disabled={state !== "idle"}
                  className="inline-flex items-center gap-1 rounded border border-tm-pos/60 bg-tm-pos/10 px-2 py-0.5 font-tm-mono text-[10px] text-tm-pos transition-opacity disabled:opacity-40 enabled:hover:bg-tm-pos/20"
                >
                  {state === "approving" ? (
                    <Loader2
                      className="h-3 w-3 animate-spin"
                      strokeWidth={1.75}
                    />
                  ) : null}
                  <span>{t(locale, "factorLab.pending.approve")}</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleReject(p)}
                  disabled={state !== "idle"}
                  className="inline-flex items-center gap-1 rounded border border-tm-rule bg-tm-bg-3 px-2 py-0.5 font-tm-mono text-[10px] text-tm-fg-2 transition-opacity disabled:opacity-40 enabled:hover:bg-tm-bg-3/60"
                >
                  {state === "rejecting" ? (
                    <Loader2
                      className="h-3 w-3 animate-spin"
                      strokeWidth={1.75}
                    />
                  ) : null}
                  <span>{t(locale, "factorLab.pending.reject")}</span>
                </button>
              </div>

              {isOpen ? (
                <div className="mt-2 ml-5 flex flex-col gap-2 rounded border border-tm-rule bg-tm-bg-2 px-3 py-2.5">
                  {symptom ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.hypothesis")}
                      </div>
                      <p className="font-tm-mono text-[11px] text-tm-fg-2">
                        {symptom}
                      </p>
                    </div>
                  ) : null}
                  {rationale ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.justification")}
                      </div>
                      <p className="font-tm-mono text-[11px] text-tm-fg-2">
                        {rationale}
                      </p>
                    </div>
                  ) : null}
                  {ev ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {t(locale, "factorLab.pending.metrics")}
                      </div>
                      <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-tm-fg-2">
                        <span>
                          dSharpe {fmtNum(ev.deflated_sharpe, 2)}
                        </span>
                        <span>IC OOS {fmtNum(ev.ic_oos, 4)}</span>
                        <span>Sharpe {fmtNum(sharpeMean, 2)}</span>
                        <span>
                          Baseline {fmtNum(ev.baseline_sharpe, 2)}
                        </span>
                        <span>
                          Folds {ev.n_folds ?? "—"}
                        </span>
                        <span>
                          Trials {ev.n_trials ?? "—"}
                        </span>
                        {typeof ev.self_correlation === "number" ? (
                          <span
                            title={
                              ev.self_correlation_with
                                ? `vs ${ev.self_correlation_with}`
                                : undefined
                            }
                          >
                            Self-corr {fmtNum(ev.self_correlation, 2)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                  {ev?.skeptic ? (
                    <div>
                      <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                        {(locale === "zh" ? "怀疑者审查 · " : "SKEPTIC · ") +
                          ev.skeptic.risk_level.toUpperCase()}
                      </div>
                      {ev.skeptic.summary ? (
                        <p className="font-tm-mono text-[11px] text-tm-fg-2">
                          {ev.skeptic.summary}
                        </p>
                      ) : null}
                      {ev.skeptic.concerns.length > 0 ? (
                        <ul className="mt-0.5 list-disc pl-4 font-tm-mono text-[10.5px] text-tm-fg-2">
                          {ev.skeptic.concerns.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                  <div>
                    <div className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
                      {t(locale, "factorLab.pending.diffVsLive")}
                    </div>
                    <pre className="overflow-x-auto rounded bg-tm-bg-3/60 p-2 font-mono text-[10px]">
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
                            {line.sign} {line.text}
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
    </TmPane>
  );
}
