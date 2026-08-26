"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Loader2,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import {
  fetchBrainRunCandidates,
  type BrainRunCandidate,
  type BrainRunCandidatePage,
} from "@/lib/api/brain";
import { TmButton, TmIconButton, TmRowButton } from "@/components/tm/TmButton";
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { TmTooltip } from "@/components/tm/TmTooltip";

type AuditFilter = "all" | "selected" | "withheld";

const REASON_LABELS: Record<string, [string, string]> = {
  selected: ["入选仿真", "selected"],
  below_evidence_threshold: ["证据分不足", "below evidence floor"],
  high_confidence_semantic_mismatch: ["高置信语义不匹配", "semantic mismatch"],
  historically_failed: ["历史机制失效", "historically weak"],
  cluster_cap: ["行为簇名额已满", "cluster cap"],
  mechanism_cap: ["机制名额已满", "mechanism cap"],
  portfolio_budget: ["仿真预算已满", "simulation budget reached"],
  withheld_by_portfolio: ["组合筛选未入选", "withheld by portfolio"],
  below_logic_threshold: ["逻辑分不足", "below logic floor"],
  llm_timeout: ["LLM 超时未入选", "withheld after LLM timeout"],
  llm_error: ["LLM 失败未入选", "withheld after LLM error"],
  llm_unscored: ["LLM 未返回评分", "not scored by LLM"],
  pending_screen: ["等待筛选", "awaiting screen"],
};

const LLM_LABELS: Record<string, [string, string]> = {
  completed: ["已评分", "scored"],
  scored: ["已评分", "scored"],
  unscored: ["未返回评分", "unscored"],
  partial: ["部分评分", "partial"],
  timeout: ["超时", "timeout"],
  error: ["失败", "failed"],
  unavailable: ["不可用", "unavailable"],
  not_configured: ["未配置", "not configured"],
  bypassed: ["未配置，使用规则筛选", "bypassed; deterministic screen"],
  pending: ["等待中", "pending"],
};

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function percent(value: unknown): string {
  const n = numberValue(value);
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

function score(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "—";
}

function evidenceOf(candidate: BrainRunCandidate): Record<string, unknown> {
  return candidate.evidence && typeof candidate.evidence === "object"
    ? candidate.evidence
    : {};
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function reasonLabel(candidate: BrainRunCandidate, zh: boolean): string {
  const key = candidate.reason_code ?? (candidate.selected ? "selected" : "pending_screen");
  const labels = REASON_LABELS[key];
  return labels ? labels[zh ? 0 : 1] : key;
}

function llmLabel(candidate: BrainRunCandidate, zh: boolean): string {
  const key = candidate.llm_status || "pending";
  const labels = LLM_LABELS[key];
  return labels ? labels[zh ? 0 : 1] : key;
}

function decisionClass(candidate: BrainRunCandidate): string {
  if (candidate.selected) return "border-tm-pos text-tm-pos";
  if (["timeout", "error"].includes(candidate.llm_status ?? "")) {
    return "border-tm-warn text-tm-warn";
  }
  return "border-tm-rule text-tm-muted";
}

function LlmState({ candidate, zh }: { candidate: BrainRunCandidate; zh: boolean }) {
  const state = candidate.llm_status || "pending";
  const cls = ["completed", "scored"].includes(state)
    ? "text-tm-pos"
    : ["timeout", "error"].includes(state)
      ? "text-tm-warn"
      : "text-tm-muted";
  return (
    <span className={`font-tm-mono text-xs ${cls}`}>
      {llmLabel(candidate, zh)}
      {candidate.llm_score != null ? ` · ${candidate.llm_score.toFixed(1)}` : ""}
    </span>
  );
}

function CandidateDetail({ candidate, zh }: { candidate: BrainRunCandidate; zh: boolean }) {
  const evidence = evidenceOf(candidate);
  const settings = Object.entries(candidate.settings ?? {});
  const missing = Array.isArray(evidence.missing_required_semantics)
    ? evidence.missing_required_semantics.map(String)
    : [];
  const metrics: Array<[string, string]> = [
    [zh ? "字段覆盖" : "field coverage", percent(evidence.coverage)],
    [zh ? "字段映射" : "field mapping", percent(evidence.mapped_ratio)],
    [zh ? "语义保真" : "semantic fidelity", percent(evidence.semantic_fidelity)],
    [zh ? "历史证据" : "history", score(numberValue(evidence.history))],
    [zh ? "上下文样本" : "context n", String(numberValue(evidence.context_n) ?? "—")],
    [zh ? "结果对齐" : "outcome alignment", score(numberValue(evidence.alignment))],
    [zh ? "集中度代理" : "concentration proxy", score(numberValue(evidence.concentration))],
    [zh ? "行为新颖性" : "behavior novelty", score(numberValue(evidence.novelty))],
  ];

  return (
    <div className="border-t border-tm-rule bg-tm-bg-2 px-10 py-3">
      <div className="grid gap-px border border-tm-rule bg-tm-rule sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label} className="bg-tm-bg px-2.5 py-2 font-tm-mono">
            <div className="text-xs uppercase tracking-wider text-tm-muted">{label}</div>
            <div className="mt-1 text-xs tabular-nums text-tm-fg">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <div>
          <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-accent">
            {zh ? "筛选判定" : "screen decision"}
          </div>
          <p className="mt-1 font-tm-mono text-xs leading-relaxed text-tm-fg-2">
            {reasonLabel(candidate, zh)}
          </p>
          {candidate.reason_text ? (
            <p className="mt-1 font-tm-mono text-xs leading-relaxed text-tm-muted">
              {candidate.reason_text}
            </p>
          ) : null}
          {missing.length > 0 ? (
            <p className="mt-1 font-tm-mono text-xs leading-relaxed text-tm-warn">
              {zh ? "缺失语义：" : "missing semantics: "}{missing.join(", ")}
            </p>
          ) : null}
        </div>
        <div>
          <div className="font-tm-mono text-xs uppercase tracking-wider text-tm-accent">
            {zh ? "仿真设置" : "simulation settings"}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {settings.length > 0 ? settings.map(([key, value]) => (
              <span key={key} className="border border-tm-rule bg-tm-bg px-1.5 py-1 font-tm-mono text-xs text-tm-fg-2">
                {key}={String(value)}
              </span>
            )) : <span className="font-tm-mono text-xs text-tm-muted">—</span>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-tm-mono text-xs text-tm-muted">
        <span>cluster={textValue(evidence.behavioral_cluster) || textValue(evidence.cluster) || "—"}</span>
        <span>lane={textValue(evidence.lane) || "—"}</span>
        <span>datasets={textValue(evidence.datasets) || "—"}</span>
        <span>proxy={String(evidence.proxy ?? "inactive")}</span>
        <span>stage={candidate.stage}</span>
      </div>
    </div>
  );
}

function CandidateRow({ candidate, zh }: { candidate: BrainRunCandidate; zh: boolean }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const evidence = evidenceOf(candidate);

  async function copyExpression(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    await navigator.clipboard.writeText(candidate.expression);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <li className="border-t border-tm-rule first:border-t-0">
      <div className="grid min-w-[980px] grid-cols-[36px_minmax(360px,1fr)_112px_72px_72px_100px_132px] items-center gap-2 px-3 py-2 hover:bg-tm-bg-2">
        <span className="font-tm-mono text-xs tabular-nums text-tm-muted">{candidate.ordinal + 1}</span>
        <TmRowButton onClick={() => setOpen((value) => !value)} aria-expanded={open} className="flex min-w-0 items-center gap-1.5">
          {open ? <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" /> : <ChevronRight className="h-3 w-3 shrink-0 text-tm-muted" />}
          <code className="truncate font-tm-mono text-xs text-tm-fg">{candidate.expression}</code>
        </TmRowButton>
        <span className="truncate font-tm-mono text-xs uppercase text-tm-fg-2" title={candidate.mechanism ?? undefined}>{candidate.mechanism || "—"}</span>
        <span className="text-right font-tm-mono text-xs tabular-nums text-tm-fg">{score(candidate.evidence_score)}</span>
        <span className="text-right font-tm-mono text-xs tabular-nums text-tm-fg-2">{percent(evidence.coverage)}</span>
        <LlmState candidate={candidate} zh={zh} />
        <span className="flex items-center justify-end gap-1.5">
          <TmIconButton
            onClick={copyExpression}
            label={zh ? "复制表达式" : "copy expression"}
            variant="secondary"
            size="sm"
            className="w-7"
            icon={copied ? <Check className="h-3 w-3 text-tm-pos" /> : <Clipboard className="h-3 w-3" />}
          />
          <span title={candidate.reason_text ?? undefined} className={`whitespace-nowrap border px-1.5 py-0.5 font-tm-mono text-xs ${decisionClass(candidate)}`}>{reasonLabel(candidate, zh)}</span>
        </span>
      </div>
      {open ? <CandidateDetail candidate={candidate} zh={zh} /> : null}
    </li>
  );
}

export function BrainCandidateAudit({
  runId,
  generatedCount,
}: {
  runId: number | null;
  generatedCount?: number | null;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [data, setData] = useState<BrainRunCandidatePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<AuditFilter>("all");
  const sequence = useRef(0);

  const load = useCallback(async () => {
    if (runId == null) {
      setData(null);
      setError(null);
      return;
    }
    const request = ++sequence.current;
    setLoading(true);
    try {
      const response = await fetchBrainRunCandidates(runId, { limit: 100 });
      if (request !== sequence.current) return;
      setData(response);
      setError(null);
    } catch (cause) {
      if (request !== sequence.current) return;
      setData(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    setData(null);
    setError(null);
    setFilter("all");
    void load();
  }, [load]);

  const candidates = useMemo(() => {
    const rows = data?.candidates ?? [];
    if (filter === "selected") return rows.filter((candidate) => candidate.selected);
    if (filter === "withheld") return rows.filter((candidate) => !candidate.selected && candidate.status !== "generated");
    return rows;
  }, [data, filter]);
  const selected = (data?.candidates ?? []).filter((candidate) => candidate.selected).length;
  const withheld = (data?.candidates ?? []).filter(
    (candidate) => !candidate.selected && candidate.status !== "generated",
  ).length;
  const llmFallbacks = (data?.candidates ?? []).filter((candidate) =>
    ["unscored", "partial", "timeout", "error"].includes(candidate.llm_status ?? ""),
  ).length;
  const llmScored = (data?.candidates ?? []).filter((candidate) =>
    candidate.llm_status === "scored" || candidate.llm_status === "completed",
  ).length;
  const simulated = (data?.candidates ?? []).filter((candidate) =>
    candidate.stage === "simulation" || candidate.simulation_outcome != null,
  ).length;
  const logicTelemetry = (data?.candidates ?? [])
    .map((candidate) => recordValue(evidenceOf(candidate).logic_screen))
    .find((value) => value != null) ?? null;
  const screenTelemetry = recordValue(logicTelemetry?.telemetry) ?? logicTelemetry;
  const totalCandidates = data?.total ?? generatedCount ?? 0;
  const timeoutSeconds = numberValue(screenTelemetry?.timeout_s);
  const provider = textValue(screenTelemetry?.provider);
  const screenStatus = textValue(logicTelemetry?.status) ?? textValue(screenTelemetry?.status);
  const mode = textValue(screenTelemetry?.mode);
  const callCount = numberValue(screenTelemetry?.call_count);
  const expressionCount = numberValue(screenTelemetry?.expression_n) ?? totalCandidates;
  const scoredCount = numberValue(screenTelemetry?.scored_n) ?? llmScored;
  const completedCalls = numberValue(screenTelemetry?.completed_calls);
  const timedOutCalls = numberValue(screenTelemetry?.timed_out_calls);
  const errorCalls = numberValue(screenTelemetry?.error_calls);
  const elapsedMs = numberValue(screenTelemetry?.elapsed_ms);
  const legacyBatchCount = numberValue(screenTelemetry?.batch_count);
  const legacyTimedOutBatches = numberValue(screenTelemetry?.timed_out_batches);
  const legacyErrorBatches = numberValue(screenTelemetry?.error_batches);
  const legacyCompletedBatches = numberValue(screenTelemetry?.completed_batches);
  const legacyRetryCount = numberValue(screenTelemetry?.retry_count);
  const legacyFailedBatchCount = (legacyTimedOutBatches ?? 0) + (legacyErrorBatches ?? 0);
  const fullPoolTelemetry = mode === "full_pool" || (mode == null && callCount === 1 && legacyBatchCount == null);

  const technicalStatusCopy = useMemo(() => {
    if (llmFallbacks <= 0) return null;
    const providerName = provider || "LLM";
    const stateCopy = screenStatus === "timeout"
      ? timeoutSeconds != null
        ? zh ? `在 ${timeoutSeconds} 秒上限后超时` : `timed out at the ${timeoutSeconds}s limit`
        : zh ? "超时" : "timed out"
      : screenStatus === "error"
        ? zh ? "调用失败" : "call failed"
        : screenStatus === "partial"
          ? zh ? "返回部分评分" : "returned partial scores"
          : screenStatus === "completed"
            ? zh ? "调用完成" : "call completed"
            : zh ? "未完整返回" : "did not return completely";
    const callCopy = fullPoolTelemetry
      ? zh
        ? `单次全池调用，完成 ${completedCalls ?? 0} 次，超时 ${timedOutCalls ?? 0} 次，错误 ${errorCalls ?? 0} 次${elapsedMs != null ? `，耗时约 ${Math.round(elapsedMs / 1000)} 秒` : ""}`
        : `one full-pool call, ${completedCalls ?? 0} completed, ${timedOutCalls ?? 0} timed out, ${errorCalls ?? 0} errored${elapsedMs != null ? `, about ${Math.round(elapsedMs / 1000)}s elapsed` : ""}`
      : legacyBatchCount != null
        ? zh
          ? `共 ${legacyBatchCount} 批，${legacyCompletedBatches ?? 0} 批完成，${legacyFailedBatchCount} 批未完成${legacyRetryCount ? `，重试 ${legacyRetryCount} 次` : ""}${elapsedMs != null ? `，耗时约 ${Math.round(elapsedMs / 1000)} 秒` : ""}`
          : `${legacyBatchCount} legacy batches, ${legacyCompletedBatches ?? 0} completed, ${legacyFailedBatchCount} incomplete${legacyRetryCount ? `, ${legacyRetryCount} retries` : ""}${elapsedMs != null ? `, about ${Math.round(elapsedMs / 1000)}s elapsed` : ""}`
        : elapsedMs != null
          ? zh ? `耗时约 ${Math.round(elapsedMs / 1000)} 秒` : `about ${Math.round(elapsedMs / 1000)}s elapsed`
          : "";
    const simulationCopy = simulated > 0
      ? zh ? `规则证据筛选入选 ${selected}/${totalCandidates} 条，其中 ${simulated} 条已完成 BRAIN 仿真。`
        : `The evidence fallback selected ${selected}/${totalCandidates}; ${simulated} completed BRAIN simulation.`
        : zh ? `规则证据筛选入选 ${selected}/${totalCandidates} 条，尚未执行 BRAIN 仿真。`
        : `The evidence fallback selected ${selected}/${totalCandidates}; BRAIN simulation has not run.`;
    const scoreCopy = scoredCount > 0
      ? zh
        ? `已取得 ${scoredCount}/${expressionCount} 条 LLM 评分；已返回评分继续有效，未评分候选仍进入 deterministic evidence screen。`
        : `LLM scores were retained for ${scoredCount}/${expressionCount}; unscored candidates still entered the deterministic evidence screen.`
      : zh
        ? `本次取得 ${scoredCount}/${expressionCount} 条 LLM 评分；未评分候选进入 deterministic evidence screen。`
        : `This call scored ${scoredCount}/${expressionCount}; unscored candidates entered the deterministic evidence screen.`;
    return zh
      ? `${providerName} 逻辑预筛${stateCopy}，${callCopy}。${scoreCopy}${simulationCopy}`
      : `${providerName} logic screening ${stateCopy}; ${callCopy}. ${scoreCopy} ${simulationCopy}`;
  }, [completedCalls, elapsedMs, errorCalls, expressionCount, fullPoolTelemetry, legacyBatchCount, legacyCompletedBatches, legacyFailedBatchCount, legacyRetryCount, llmFallbacks, provider, screenStatus, scoredCount, selected, simulated, timedOutCalls, timeoutSeconds, totalCandidates, zh]);

  if (runId == null) {
    return (
      <div className="px-3 py-8 text-center font-tm-mono text-xs text-tm-muted">
        {zh ? "选择一个 RUN 后查看生成池与筛选证据。" : "Select a run to inspect its generated pool and screen evidence."}
      </div>
    );
  }

  return (
    <section aria-label={zh ? "候选审计" : "candidate audit"}>
      <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
        <TmToggleGroup<AuditFilter>
          value={filter}
          onChange={setFilter}
          ariaLabel={zh ? "候选审计筛选" : "Candidate audit filter"}
          options={[
            {
              value: "all",
              label: <>{zh ? "全部候选" : "all candidates"} <span className="tabular-nums">{data?.total ?? generatedCount ?? 0}</span></>,
            },
            {
              value: "selected",
              label: <>{zh ? "入选" : "selected"} <span className="tabular-nums">{selected}</span></>,
            },
            {
              value: "withheld",
              label: <>{zh ? "未入选" : "withheld"} <span className="tabular-nums">{withheld}</span></>,
            },
          ]}
        />
        <TmButton
          type="button"
          variant="secondary"
          size="xs"
          loading={loading}
          loadingLabel={zh ? "刷新中" : "refreshing"}
          onClick={() => void load()}
          className="ml-auto"
        >
          <RefreshCw className="h-3 w-3" />
          {zh ? "刷新审计" : "refresh audit"}
        </TmButton>
      </div>

      {llmFallbacks > 0 ? (
        <div className="flex items-start gap-2 border-b border-tm-warn/40 bg-tm-warn/5 px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-warn" role="status">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{technicalStatusCopy}</span>
        </div>
      ) : null}

      {loading && data == null ? (
        <div className="flex items-center gap-2 px-3 py-6 font-tm-mono text-xs text-tm-muted" role="status">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {zh ? "正在读取本轮候选审计账本…" : "Loading this run's candidate audit ledger…"}
        </div>
      ) : error ? (
        <div className="flex items-start gap-2 px-3 py-5 font-tm-mono text-xs leading-relaxed text-tm-neg" role="alert">
          <X className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="inline-flex items-center gap-2">
            {zh ? `候选审计读取失败：${error}` : `Candidate audit failed to load: ${error}`}
            <TmButton variant="danger" size="xs" onClick={() => void load()}>
              {zh ? "重试" : "retry"}
            </TmButton>
          </span>
        </div>
      ) : data && data.total === 0 ? (
        <div className="px-3 py-6 font-tm-mono text-xs leading-relaxed text-tm-muted">
          {(generatedCount ?? 0) > 0
            ? zh
              ? "这轮发生在候选审计账本上线前，或 worker 尚未写入候选明细。聚合数量仍在，但表达式与逐条筛选原因无法从旧数据恢复。"
              : "This run predates the candidate ledger, or its worker did not write candidate rows. Aggregate counts remain, but expressions and per-candidate decisions cannot be recovered."
            : zh
              ? "本轮尚未生成候选。"
              : "This run has not generated candidates yet."}
        </div>
      ) : data ? (
        <>
          <div className="overflow-x-auto">
            <div className="grid min-w-[980px] grid-cols-[36px_minmax(360px,1fr)_112px_72px_72px_100px_132px] items-center gap-2 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
              <span>#</span>
              <span>{zh ? "候选表达式" : "candidate expression"}</span>
              <span>{zh ? "机制" : "mechanism"}</span>
              <TmTooltip content={zh ? "筛选前的综合研究证据分，不是 BRAIN 官方指标。" : "Pre-simulation research evidence score, not an official BRAIN metric."} className="justify-end">
                <span className="cursor-help text-right">{zh ? "证据" : "evidence"}</span>
              </TmTooltip>
              <TmTooltip content={zh ? "表达式字段在官方目录元数据中的可核验覆盖率。" : "Verifiable coverage of expression fields in official catalog metadata."} className="justify-end">
                <span className="cursor-help text-right">{zh ? "覆盖" : "coverage"}</span>
              </TmTooltip>
              <TmTooltip content={zh ? "LLM 筛选器的技术状态，与因子经济质量分开记录。" : "Technical state of the LLM screen, recorded separately from economic quality."}>
                <span className="cursor-help">LLM</span>
              </TmTooltip>
              <span className="text-right">{zh ? "筛选结论" : "decision"}</span>
            </div>
            {candidates.length > 0 ? (
              <ul>
                {candidates.map((candidate) => (
                  <CandidateRow key={candidate.id} candidate={candidate} zh={zh} />
                ))}
              </ul>
            ) : (
              <div className="px-3 py-6 text-center font-tm-mono text-xs text-tm-muted">
                {zh ? "当前筛选条件下没有候选。" : "No candidates match this audit filter."}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-tm-rule px-3 py-2 font-tm-mono text-xs text-tm-muted">
            <span>
              {zh
                ? `共 ${data.total} 条，入选 ${selected} 条，未入选 ${withheld} 条。`
                : `${data.total} total, ${selected} selected, ${withheld} withheld.`}
            </span>
            <span>{zh ? "未入选候选不会消耗 BRAIN 仿真预算。" : "Withheld candidates do not consume BRAIN simulation budget."}</span>
          </div>
        </>
      ) : null}
    </section>
  );
}
