"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Send,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  Clipboard,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { SegmentedTabs } from "@/components/ui/SegmentedTabs";
import { BrainPnLChart, type ChartKind } from "@/components/brain/BrainPnLChart";
import { BrainCandidateAudit } from "@/components/brain/BrainCandidateAudit";
import { TmPagination } from "@/components/tm/TmPagination";
import { TmSelectMenu } from "@/components/tm/TmSelectMenu";
import { TmStatePane } from "@/components/tm/TmStatePane";
import { TmButton, TmRowButton } from "@/components/tm/TmButton";
import { TmInput } from "@/components/tm/TmField";
import { TmToggleGroup } from "@/components/tm/TmToggleGroup";
import { TmTooltip } from "@/components/tm/TmTooltip";
import { WorkbenchHeader } from "@/components/workbench/WorkbenchHeader";
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
import { Play } from "lucide-react";
import {
  fetchBrainAlphas,
  fetchBrainRuns,
  fetchAlphaPnl,
  fetchAlphaYearly,
  fetchMineStatus,
  submitBrainAlpha,
  triggerMining,
  type BrainAlpha,
  type BrainAlphaQuery,
  type BrainMiningRun,
  type BrainOutcome,
  type PnlPoint,
  type YearlyRow,
} from "@/lib/api/brain";
import { DEFAULT_BRAIN_PAGE_SIZE, brainSubmissionState, familyLabel, hasUnsimulatedCandidates, nextExpandedAlpha, runFailureAction, type BrainSubmissionState } from "./brain-review";

type WorkbenchView = "results" | "audit";

// Format an ISO timestamp as Beijing time (UTC+8), to the second.
function fmtUtc8(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const t = new Date(d.getTime() + 8 * 3600 * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${t.getUTCFullYear()}-${p(t.getUTCMonth() + 1)}-${p(t.getUTCDate())} ` +
    `${p(t.getUTCHours())}:${p(t.getUTCMinutes())}:${p(t.getUTCSeconds())}`
  );
}

// ── in-flight mining tracker (survives refresh / navigation) ─────────────────
type ActiveJob = {
  startedAt: string;
  n: number;
  generationTarget?: number;
  dispatchedAt: number;
  /** Optional so jobs saved by the pre-run-ledger UI still resume safely. */
  runId?: number | null;
};
const LS_ACTIVE_MINING = "brain.activeMining.v1";
const POLL_MS = 25_000;
// Before this grace window we don't trust running=false (the GH run may not have
// appeared yet). After it, "no active run" means the round is done.
const GRACE_MS = 3 * 60_000;
// Hard safety cap so a failed/stuck run can never lock the button forever.
const MAX_TRACK_MS = 75 * 60_000;

function loadActiveJob(): ActiveJob | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LS_ACTIVE_MINING);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ActiveJob>;
    if (
      typeof value.startedAt !== "string" ||
      typeof value.n !== "number" ||
      typeof value.dispatchedAt !== "number"
    ) {
      return null;
    }
    return {
      startedAt: value.startedAt,
      n: value.n,
      generationTarget:
        typeof value.generationTarget === "number" ? value.generationTarget : undefined,
      dispatchedAt: value.dispatchedAt,
      runId: typeof value.runId === "number" ? value.runId : undefined,
    };
  } catch {
    return null;
  }
}

function saveActiveJob(job: ActiveJob | null): void {
  if (typeof window === "undefined") return;
  try {
    if (job) window.localStorage.setItem(LS_ACTIVE_MINING, JSON.stringify(job));
    else window.localStorage.removeItem(LS_ACTIVE_MINING);
  } catch {
    /* private mode / quota — tracking just won't persist across reloads */
  }
}

function fmt(v: number | null | undefined, d = 2): string {
  return typeof v === "number" && !Number.isNaN(v) ? v.toFixed(d) : "—";
}

const OUTCOME_CLS: Record<BrainOutcome, string> = {
  passed: "border-tm-pos text-tm-pos",
  flagged: "border-tm-warn text-tm-warn",
  rejected: "border-tm-rule text-tm-muted",
  sim_error: "border-tm-neg text-tm-neg",
};

function outcomeLabel(o: BrainOutcome, zh: boolean): string {
  return zh
    ? { passed: "通过", flagged: "存疑", rejected: "淘汰", sim_error: "错误" }[o]
    : { passed: "Passed", flagged: "Flagged", rejected: "Rejected", sim_error: "Sim error" }[o];
}

type CandidateVerdict = {
  labelZh: string;
  labelEn: string;
  detailZh: string;
  detailEn: string;
  cls: string;
};

function candidateVerdict(alpha: BrainAlpha): CandidateVerdict {
  const corr = Math.max(
    alpha.self_correlation ?? 0,
    alpha.self_correlation_adj ?? 0,
  );
  const highQuality =
    ["EXCELLENT", "SPECTACULAR"].includes(alpha.grade ?? "") ||
    ((alpha.sharpe ?? 0) >= 1.25 && (alpha.fitness ?? 0) >= 1);
  if (alpha.outcome === "flagged" && corr >= 0.70 && highQuality) {
    return {
      labelZh: "高质·冗余",
      labelEn: "STRONG·REDUNDANT",
      detailZh: "绩效门槛已通过，但收益路径与现有因子高度重合。下一轮应切换经济机制或数据子集，而不是只改窗口。",
      detailEn: "Performance gates passed, but the return path overlaps the existing book. Switch mechanism or data, not only windows.",
      cls: "border-tm-warn text-tm-warn",
    };
  }
  if (alpha.outcome === "passed" && corr >= 0.65 && corr < 0.70) {
    return {
      labelZh: "通过·近门槛",
      labelEn: "PASS·WATCH",
      detailZh: "该因子仍低于 BRAIN 官方 0.70 自相关硬门槛，因此保留通过；但已进入 0.65–0.70 预警带，组合纳入时应优先检查它是否提供足够的边际贡献。",
      detailEn: "This factor remains below BRAIN's official 0.70 hard limit and passes, but sits in the 0.65–0.70 warning band. Review its marginal portfolio contribution before promotion.",
      cls: "border-tm-warn text-tm-warn",
    };
  }
  if (alpha.outcome === "flagged" && alpha.detail?.includes("family") && alpha.detail?.includes("saturated")) {
    return {
      labelZh: "家族饱和",
      labelEn: "SATURATED",
      detailZh: "同一经济家族的代表数已达上限。保留本结果作证据，但不视为新的组合贡献。",
      detailEn: "This economic family has reached its representative cap; keep as evidence, not new portfolio contribution.",
      cls: "border-tm-warn text-tm-warn",
    };
  }
  return {
    labelZh: outcomeLabel(alpha.outcome, true),
    labelEn: outcomeLabel(alpha.outcome, false),
    detailZh: alpha.detail || "暂无额外诊断。",
    detailEn: alpha.detail || "No additional diagnosis.",
    cls: OUTCOME_CLS[alpha.outcome],
  };
}

// ── submit control (two-step confirm, matches the app's forgiveness pattern) ──
type SubmitState = "idle" | "confirm" | "sending" | "error" | BrainSubmissionState;

function SubmitControl({ alpha, onDone }: { alpha: BrainAlpha; onDone: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [state, setState] = useState<SubmitState>("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const recorded = brainSubmissionState(alpha);
  const result = state === "accepted" || state === "rejected" ? state : recorded;

  if (result) {
    return (
      <span role="status" className={`inline-flex items-center gap-1.5 font-tm-mono text-xs ${result === "accepted" ? "text-tm-pos" : result === "rejected" ? "text-tm-neg" : "text-tm-muted"}`}>
        {result === "accepted" ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : null}
        {result === "accepted"
          ? (zh ? "BRAIN 已受理" : "Accepted by BRAIN")
          : result === "rejected"
            ? (zh ? "BRAIN 未接受本次提交" : "BRAIN rejected this submission")
            : (zh ? "已尝试提交，未确认受理" : "Submission attempted; acceptance unconfirmed")}
      </span>
    );
  }

  async function doSubmit() {
    setState("sending");
    try {
      const r = await submitBrainAlpha(alpha.id);
      setState(brainSubmissionState(r) ?? "attempted");
      onDone();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

  if (alpha.outcome !== "passed" && alpha.outcome !== "flagged") return null;

  return (
    <div className="flex items-center gap-2">
      {state === "confirm" ? (
        <>
          <TmButton
            onClick={doSubmit}
            variant="primary"
            size="xs"
          >
            <Send className="h-3 w-3" strokeWidth={2} />
            {zh ? "确认提交" : "Confirm"}
          </TmButton>
          <TmButton
            onClick={() => setState("idle")}
            variant="ghost"
            size="xs"
          >
            {zh ? "取消" : "cancel"}
          </TmButton>
        </>
      ) : (
        <TmButton
          onClick={() => setState("confirm")}
          loading={state === "sending"}
          loadingLabel={zh ? "提交中" : "Submitting"}
          variant="secondary"
          size="xs"
        >
          {state === "sending" ? (
            <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
          ) : (
            <Send className="h-3 w-3" strokeWidth={1.75} />
          )}
          {zh ? "提交到 BRAIN" : "Submit to BRAIN"}
        </TmButton>
      )}
      {state === "error" && msg ? (
        <span className="font-tm-mono text-xs text-tm-neg">{msg}</span>
      ) : null}
    </div>
  );
}

// ── expandable row detail: PnL chart + full metrics + submit ─────────────────
// simulation-settings row (from the stored settings jsonb — what BRAIN
// actually simulated the alpha with).
function SettingsRow({ settings }: { settings: Record<string, unknown> }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const s = settings || {};
  const g = (k: string): string => (s[k] === undefined || s[k] === null ? "—" : String(s[k]));
  const cells: Array<[string, string]> = [
    [zh ? "地区" : "Region", g("region")],
    [zh ? "股池" : "Universe", g("universe")],
    ["Decay", g("decay")],
    ["Delay", g("delay")],
    [zh ? "中性化" : "Neutralization", g("neutralization")],
    ["Truncation", g("truncation")],
    ["Pasteurization", g("pasteurization")],
    [zh ? "语言" : "Language", g("language")],
  ];
  return (
    <div>
      <div className="mb-1 font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
        {zh ? "仿真参数" : "Simulation settings"}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        {cells.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 font-mono text-xs">
            <span className="text-tm-muted">{k}</span>
            <span className="tabular-nums text-tm-fg-2">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ResearchEvidencePanel({ alpha }: { alpha: BrainAlpha }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const evidence = alpha.research_evidence;
  if (!evidence) return null;
  const hypothesis = evidence.hypothesis;
  const mapping = evidence.field_mapping;
  const semantic = evidence.semantic_audit;
  const screen = evidence.screen;
  const proxy = evidence.proxy;
  const pct = (value: number | undefined) =>
    typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
  const prediction = proxy?.prediction || {};
  const semanticTone = semantic?.status === "matched"
    ? "text-tm-pos"
    : semantic?.status === "mismatch"
      ? "text-tm-neg"
      : "text-tm-warn";
  const semanticLabel = semantic?.status === "matched"
    ? (zh ? "语义匹配" : "semantics matched")
    : semantic?.status === "mismatch"
      ? (zh ? "语义不匹配" : "semantic mismatch")
      : (zh ? "语义待核验" : "semantics unverified");
  const alignmentStatus = semantic?.target_outcome_alignment?.status;
  const alignmentLabel = alignmentStatus === "aligned"
    ? (zh ? "目标对齐" : "target aligned")
    : alignmentStatus === "exploratory_mismatch"
      ? (zh ? "仅探索，目标不一致" : "exploratory target mismatch")
      : (zh ? "目标待核验" : "target unverified");
  return (
    <div className="border border-tm-rule bg-tm-bg px-3 py-2.5">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-tm-mono text-xs uppercase tracking-wider text-tm-accent">
          {zh ? "研究证据" : "Research evidence"}
        </span>
        <span className="font-tm-mono text-xs text-tm-muted">
          {proxy?.active
            ? `${zh ? "代理已验证" : "proxy validated"} · n=${proxy.sample_n ?? "—"}`
            : zh
              ? "代理未启用，使用分层后验"
              : "proxy inactive; hierarchical posterior used"}
        </span>
      </div>
      <div className="grid gap-3 text-xs lg:grid-cols-4">
        <div>
          <div className="font-tm-mono text-xs uppercase text-tm-muted">
            {zh ? "假设" : "Hypothesis"}
          </div>
          {hypothesis?.source_url ? (
            <a
              href={hypothesis.source_url}
              target="_blank"
              rel="noreferrer"
              className="text-tm-fg hover:text-tm-accent"
            >
              {hypothesis.title || hypothesis.id}
            </a>
          ) : (
            <div className="text-tm-fg">{hypothesis?.title || hypothesis?.id || "—"}</div>
          )}
          <div className="mt-1 font-tm-mono text-xs text-tm-muted">
            {hypothesis?.confidence || "—"} · {hypothesis?.target || "—"}
          </div>
          {semantic ? (
            <TmTooltip
              content={semantic.target_outcome_alignment?.target || alignmentLabel}
              ariaLabel={alignmentLabel}
              className="mt-1"
            >
              <span className={`font-tm-mono text-xs ${alignmentStatus === "aligned" ? "text-tm-pos" : "text-tm-warn"}`}>
                {alignmentLabel}
              </span>
            </TmTooltip>
          ) : null}
        </div>
        <div>
          <div className="font-tm-mono text-xs uppercase text-tm-muted">
            {zh ? "字段可测量性" : "Field measurability"}
          </div>
          <div className="font-tm-mono text-tm-fg">
            {mapping?.dataset_ids?.join(" + ") || "unmapped"}
          </div>
          <div className="mt-1 font-tm-mono text-xs text-tm-muted">
            coverage {pct(mapping?.coverage)} · mapped {pct(mapping?.mapped_ratio)}
          </div>
          {semantic ? (
            <>
              <div className={`mt-1 font-tm-mono text-xs ${semanticTone}`}>
                {semanticLabel} · {semantic.matched_required_semantics?.length ?? 0}/{semantic.required_semantics?.length ?? 0}
              </div>
              {semantic.missing_required_semantics?.length ? (
                <TmTooltip content={semantic.missing_required_semantics.join(" · ")} className="mt-1 max-w-full">
                  <span className="truncate font-tm-mono text-xs text-tm-neg">
                    {zh ? "缺失" : "missing"}: {semantic.missing_required_semantics.join(", ")}
                  </span>
                </TmTooltip>
              ) : null}
            </>
          ) : null}
        </div>
        <div>
          <div className="font-tm-mono text-xs uppercase text-tm-muted">
            {zh ? "筛选证据" : "Screen evidence"}
          </div>
          <div className="font-tm-mono text-tm-fg">
            score {typeof screen?.score === "number" ? screen.score.toFixed(2) : "—"}
          </div>
          <div className="mt-1 font-tm-mono text-xs text-tm-muted">
            history {typeof screen?.history === "number" ? screen.history.toFixed(2) : "—"} · context n={screen?.context_n ?? 0}
          </div>
        </div>
        <div>
          <div className="font-tm-mono text-xs uppercase text-tm-muted">
            {zh ? "代理预测" : "Proxy prediction"}
          </div>
          {proxy?.active ? (
            <>
              <div className="font-tm-mono text-tm-fg">
                GOOD {pct(prediction.good)} · {zh ? "集中风险" : "concentration"} {pct(prediction.concentration)}
              </div>
              <div className="mt-1 font-tm-mono text-xs text-tm-muted">
                {zh ? "官方自相关估计" : "official self-corr estimate"} {pct(prediction.self_corr)} · {zh ? "分散化代理" : "diversification proxy"} {pct(prediction.marginal_proxy)}
              </div>
              <TmTooltip
                className="mt-1"
                content={zh
                  ? "分散化代理为 1 − 调整后自相关²，并非真实组合边际收益回归。"
                  : "Diversification proxy is 1 minus adjusted self-correlation squared, not a portfolio-level incremental-return regression."}
              >
                <span className="font-tm-mono text-xs text-tm-muted">
                  {zh ? "近 20% 时间留出集验证，仅以 15% 权重参与预筛" : "validated on the latest 20% holdout; 15% screen weight"}
                </span>
              </TmTooltip>
            </>
          ) : (
            <TmTooltip content={proxy?.reason || (zh ? "未通过样本或留出验证门槛" : "sample or holdout gate not met")}>
              <span className="text-tm-muted">
                {zh ? "未通过样本或留出验证门槛" : "sample or holdout gate not met"}
              </span>
            </TmTooltip>
          )}
        </div>
      </div>
      {hypothesis?.falsification ? (
        <div className="mt-2 border-t border-tm-rule pt-2 font-tm-mono text-xs text-tm-muted">
          {zh ? "证伪条件" : "Falsification"}: {hypothesis.falsification}
        </div>
      ) : null}
    </div>
  );
}

// per-year IS Summary table (fetched from BRAIN on demand).
const YEARLY_COLS = [
  "year", "sharpe", "turnover", "fitness", "returns", "drawdown", "margin",
  "longCount", "shortCount",
];

function YearlyTable({ rowId, hasAlpha }: { rowId: number; hasAlpha: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [rows, setRows] = useState<YearlyRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!hasAlpha) return;
    let alive = true;
    fetchAlphaYearly(rowId)
      .then((r) => alive && setRows(r.rows))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [rowId, hasAlpha]);

  if (!hasAlpha) return null;
  const cols = rows && rows.length > 0
    ? YEARLY_COLS.filter((c) => c in rows[0])
    : YEARLY_COLS;

  return (
    <div>
      <div className="mb-1 font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
        {zh ? "历年 IS 概要" : "IS Summary by year"}
      </div>
      {rows && rows.length > 0 ? (
        <TmTableFrame>
          <TmTable
            density="compact"
            caption={zh ? "历年 IS 概要" : "IS Summary by year"}
            className="min-w-[560px] text-xs"
          >
            <TmTableHead>
              <TmTableRow>
                {cols.map((c, index) => (
                  <TmTableHeaderCell
                    key={c}
                    textAlign={index === 0 ? "left" : "right"}
                    className="px-2 text-xs"
                  >
                    {c}
                  </TmTableHeaderCell>
                ))}
              </TmTableRow>
            </TmTableHead>
            <TmTableBody>
              {rows.map((r, i) => (
                <TmTableRow key={i}>
                  {cols.map((c, index) => {
                    const value = r[c] === null || r[c] === undefined
                      ? "—"
                      : typeof r[c] === "number"
                      ? (r[c] as number).toFixed(c === "year" ? 0 : 2)
                      : String(r[c]);
                    return index === 0 ? (
                      <TmTableRowHeader key={c} className="px-2 font-normal">
                        {value}
                      </TmTableRowHeader>
                    ) : (
                      <TmTableCell key={c} numeric textAlign="right" className="px-2 text-tm-fg-2">
                        {value}
                      </TmTableCell>
                    );
                  })}
                </TmTableRow>
              ))}
            </TmTableBody>
          </TmTable>
        </TmTableFrame>
      ) : err ? (
        <TmStatePane
          state="empty"
          title={zh ? "无历年数据" : "No yearly data"}
          className="min-h-20 rounded-none border-0"
        />
      ) : (
        <TmStatePane
          state="loading"
          title={zh ? "拉取历年数据…" : "Fetching yearly data…"}
          className="min-h-20 rounded-none border-0"
        />
      )}
    </div>
  );
}

function RowDetail({ alpha, onDone }: { alpha: BrainAlpha; onDone: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [pnl, setPnl] = useState<PnlPoint[] | null>(null);
  const [pnlErr, setPnlErr] = useState<string | null>(null);
  const [chartKind, setChartKind] = useState<ChartKind>("pnl");
  const verdict = candidateVerdict(alpha);

  useEffect(() => {
    let alive = true;
    if (!alpha.alpha_id) {
      setPnlErr(zh ? "此候选无 BRAIN alpha(仿真失败)" : "no BRAIN alpha (sim failed)");
      return;
    }
    fetchAlphaPnl(alpha.id)
      .then((r) => alive && setPnl(r.points))
      .catch((e) => alive && setPnlErr(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [alpha.id, alpha.alpha_id, zh]);

  const CHART_KINDS: Array<[ChartKind, string]> = [
    ["pnl", "PnL"],
    ["sharpe", zh ? "滚动 Sharpe" : "Sharpe"],
    ["drawdown", "Drawdown"],
  ];

  return (
    <div className="flex flex-col gap-3 border-t border-tm-rule bg-tm-bg-2 px-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <code className={`min-w-0 flex-1 break-all font-tm-mono text-xs leading-snug ${alpha.is_blend ? "text-tm-accent" : "text-tm-fg"}`}>
          {alpha.expression}
        </code>
        {alpha.alpha_id ? <AlphaIdChip alphaId={alpha.alpha_id} /> : null}
      </div>

      {/* Blend provenance: this candidate was stitched from real parent alphas
          (family_focus == "blend" round). Old rows have no blend_parents and
          never render this — we don't retro-tag historical blends. */}
      {alpha.is_blend && alpha.blend_parents && alpha.blend_parents.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="rounded-sm border border-tm-accent/60 px-1.5 py-px font-tm-mono text-xs font-bold uppercase text-tm-accent">
              BLEND
            </span>
            <span className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
              {zh ? "父因子" : "parents"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            {alpha.blend_parents.map((p, i) => (
              <code
                key={i}
                className="block break-all font-tm-mono text-xs leading-snug text-tm-muted"
              >
                {p}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {/* BRAIN's overall performance grade for this alpha + record timestamp */}
      <div className="flex items-center gap-2">
        <span className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
          {zh ? "性能评级" : "performance"}
        </span>
        <GradeBadge grade={alpha.grade} full />
        <span className="font-tm-mono text-xs text-tm-muted">
          {zh ? "BRAIN 综合评级" : "BRAIN overall grade"}
        </span>
        {alpha.created_at ? (
          <TmTooltip content={zh ? "该回测结果记录时间（UTC+8）" : "Backtest record time (UTC+8)"} className="ml-auto">
            <span className="flex items-center gap-1 font-tm-mono text-xs tabular-nums text-tm-muted">
              {fmtUtc8(alpha.created_at)}
              <span className="opacity-60">UTC+8</span>
            </span>
          </TmTooltip>
        ) : null}
      </div>

      {/* why rejected (failing checks) + retried tag */}
      <OutcomeTags alpha={alpha} />

      <div className="grid border border-tm-rule sm:grid-cols-[150px_1fr]">
        <div className="flex items-center border-b border-tm-rule px-3 py-2 sm:border-b-0 sm:border-r">
          <span className={`border px-1.5 py-px font-tm-mono text-xs font-bold uppercase ${verdict.cls}`}>
            {zh ? verdict.labelZh : verdict.labelEn}
          </span>
        </div>
        <div className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere] px-3 py-2 font-tm-mono text-xs leading-relaxed text-tm-fg-2">
          {zh ? verdict.detailZh : verdict.detailEn}
          {alpha.detail && alpha.detail !== verdict.detailEn ? (
            <details className="mt-1 text-tm-muted">
              <summary className="cursor-pointer">{zh ? "原始诊断" : "Raw diagnosis"}</summary>
              {alpha.detail}
            </details>
          ) : null}
        </div>
      </div>

      {/* full IS metric set (6) + self-corr + BRAIN id */}
      <div className="grid grid-cols-3 gap-2 font-mono text-xs text-tm-fg-2 sm:grid-cols-4 lg:grid-cols-8">
        <Metric label="Sharpe" value={fmt(alpha.sharpe)} />
        <Metric label="Fitness" value={fmt(alpha.fitness)} />
        <Metric label={zh ? "换手" : "Turnover"} value={fmt(alpha.turnover)} />
        <Metric label={zh ? "收益" : "Returns"} value={fmt(alpha.returns)} />
        <Metric label={zh ? "回撤" : "Drawdown"} value={fmt(alpha.drawdown)} />
        <Metric label={zh ? "边际收益" : "Margin"} value={fmt(alpha.margin, 4)} />
        <div className="flex flex-col">
          <span className="font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-muted">
            {zh ? "自相关·官方" : "S-corr (BRAIN)"}
          </span>
          <span className="tabular-nums text-tm-fg">
            <OfficialSCorrCell alpha={alpha} zh={zh} />
          </span>
        </div>
        <div className="flex flex-col">
          <span className="font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-muted">
            {zh ? "自相关·调整" : "S-corr⁺ (adj)"}
          </span>
          <span className="tabular-nums">
            <SCorrValue value={alpha.self_correlation_adj} />
          </span>
        </div>
      </div>

      <SettingsRow settings={alpha.settings} />
      <ResearchEvidencePanel alpha={alpha} />

      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
            {zh ? "曲线" : "chart"}
          </span>
          <TmToggleGroup
            value={chartKind}
            onChange={setChartKind}
            ariaLabel={zh ? "曲线类型" : "Chart kind"}
            options={CHART_KINDS.map(([value, label]) => ({ value, label }))}
          />
        </div>
        {pnl && pnl.length > 0 ? (
          <BrainPnLChart points={pnl} kind={chartKind} />
        ) : pnlErr ? (
          <p className="font-tm-mono text-xs text-tm-muted">{pnlErr}</p>
        ) : (
          <p className="flex items-center gap-2 font-tm-mono text-xs text-tm-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {zh ? "从 BRAIN 拉取 PnL…" : "fetching PnL from BRAIN…"}
          </p>
        )}
      </div>

      <YearlyTable rowId={alpha.id} hasAlpha={Boolean(alpha.alpha_id)} />

      <div className="flex justify-end">
        <SubmitControl alpha={alpha} onDone={onDone} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-tm-mono text-xs uppercase tracking-[0.08em] text-tm-muted">
        {label}
      </span>
      <span className="tabular-nums text-tm-fg">{value}</span>
    </div>
  );
}

// BRAIN's performance tier for the alpha. Colored best→worst; unknown grades
// render as-is (never invent a tier). `short` keeps the row column compact.
const GRADE_STYLE: Record<string, { cls: string; short: string }> = {
  SPECTACULAR: { cls: "border-tm-accent text-tm-accent", short: "SPEC" },
  EXCELLENT: { cls: "border-tm-pos text-tm-pos", short: "EXCL" },
  GOOD: { cls: "border-tm-info text-tm-info", short: "GOOD" },
  AVERAGE: { cls: "border-tm-rule text-tm-fg-2", short: "AVG" },
  INFERIOR: { cls: "border-tm-warn text-tm-warn", short: "INFR" },
  POOR: { cls: "border-tm-neg text-tm-neg", short: "POOR" },
};

function SCorrValue({ value }: { value: number | null }) {
  if (typeof value !== "number") return <>—</>;
  const cls = value >= 0.70
    ? "text-tm-neg"
    : value >= 0.65
      ? "text-tm-warn"
      : "text-tm-fg";
  return <span className={cls}>{fmt(value)}</span>;
}

// Official BRAIN self-correlation. The API computes this lazily, so a missing
// value must retain its actual pipeline state rather than collapsing to “pending”.
function OfficialSCorrCell({ alpha, zh }: { alpha: BrainAlpha; zh: boolean }) {
  if (typeof alpha.self_correlation === "number") {
    return <SCorrValue value={alpha.self_correlation} />;
  }
  const status = alpha.self_correlation_status ?? (
    alpha.outcome === "rejected" && alpha.fail_checks
      ? "skipped_prerequisite"
      : "pending"
  );
  if (status === "skipped_prerequisite") {
    return (
      <TmTooltip
        content={
          zh
            ? "该因子先未通过 BRAIN 的持仓集中度、子股票池 Sharpe 等提交前置检查，因此主流程未执行自相关请求。GOOD 及以上结果会在轮次末尾进入限量补查。"
            : "This factor failed an earlier BRAIN submission prerequisite, so the main path skipped the self-correlation request. GOOD-or-better rows enter a bounded post-run enrichment pass."
        }
      >
        <span className="cursor-help text-tm-muted">{zh ? "未执行" : "skipped"}</span>
      </TmTooltip>
    );
  }
  if (status === "unavailable") {
    return (
      <TmTooltip
        content={
          zh
            ? "已请求 BRAIN 官方自相关，但在本轮限时轮询内尚未返回。后台回填任务会继续重试。"
            : "Official self-correlation was requested but did not settle within the bounded poll. The scheduled backfill will retry."
        }
      >
        <span className="cursor-help text-tm-warn">{zh ? "暂不可用" : "unavail"}</span>
      </TmTooltip>
    );
  }
  return (
    <TmTooltip
      content={
        zh
          ? "BRAIN 官方自相关正在等待计算或尚未进入补查队列。0.70 是官方硬门槛，0.65–0.70 仅作预警。"
          : "Official BRAIN self-correlation is waiting to compute or has not entered enrichment yet. 0.70 is the hard limit; 0.65–0.70 is warning-only."
      }
    >
      <span className="cursor-help text-tm-muted">{zh ? "待计算" : "pending"}</span>
    </TmTooltip>
  );
}

// Economic family of the alpha (from evolution.family_of, server-side). Labels
// mirror the FamilySelect dropdown so the same family reads the same everywhere.
// The six value-orthogonal sources get an accent-tinted border (the families we
// WANT); the saturated 'value'/'other' cluster stays muted.
const FAMILY_SATURATED = new Set(["value", "other"]);
// When `onClick` is passed the badge becomes a family filter toggle (click to
// filter to that family, click the active one to clear). `active` highlights the
// badge whose family is the current filter.
function FamilyBadge({
  family,
  onClick,
  active = false,
}: {
  family?: string | null;
  onClick?: (fam: string) => void;
  active?: boolean;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  if (!family) return null;
  const label = familyLabel(family, zh);
  const base = FAMILY_SATURATED.has(family)
    ? "border-tm-rule text-tm-muted"
    : "border-tm-accent/40 text-tm-fg-2";
  const cls = active ? "border-tm-accent text-tm-accent" : base;
  const shape = "shrink-0 border px-1 py-px font-tm-mono text-xs uppercase leading-none";
  if (!onClick) {
    return (
      <TmTooltip content={family} width={180}>
        <span className={`${shape} ${cls}`}>{label}</span>
      </TmTooltip>
    );
  }
  return (
    <TmButton
      variant="ghost"
      size="xs"
      aria-pressed={active}
      aria-label={active ? (zh ? `清除${label}筛选` : `Clear ${label} filter`) : (zh ? `筛选：${label}` : `Filter: ${label}`)}
      onClick={(e) => {
        e.stopPropagation();
        onClick(family);
      }}
      className={`h-4 border px-1 text-xs leading-none hover:border-tm-accent ${cls}`}
    >
      {label}
    </TmButton>
  );
}

function GradeBadge({ grade, full = false }: { grade: string | null; full?: boolean }) {
  const { locale } = useLocale();
  if (!grade) {
    return <span className="font-tm-mono text-xs text-tm-muted">—</span>;
  }
  const s = GRADE_STYLE[grade.toUpperCase()];
  const labels: Record<string, string> = { SPECTACULAR: "卓越", EXCELLENT: "优秀", GOOD: "良好", AVERAGE: "一般", INFERIOR: "偏弱", POOR: "较差" };
  const label = locale === "zh" ? labels[grade.toUpperCase()] ?? grade : full ? grade : (s?.short ?? grade);
  const cls = s?.cls ?? "border-tm-rule text-tm-muted";
  return (
    <TmTooltip content={grade}>
      <span className={`border px-1 py-px font-tm-mono text-xs font-bold uppercase ${cls}`}>
        {label}
      </span>
    </TmTooltip>
  );
}

// Friendly labels for BRAIN's in-sample check names (why a factor was rejected).
const CHECK_LABELS: Record<string, { zh: string; en: string }> = {
  LOW_SHARPE: { zh: "Sharpe 偏低", en: "low Sharpe" },
  LOW_FITNESS: { zh: "Fitness 偏低", en: "low Fitness" },
  HIGH_TURNOVER: { zh: "换手过高", en: "high turnover" },
  LOW_TURNOVER: { zh: "换手过低", en: "low turnover" },
  HIGH_DRAWDOWN: { zh: "回撤过大", en: "high drawdown" },
  CONCENTRATED_WEIGHT: { zh: "持仓过于集中", en: "concentrated" },
  LOW_SUB_UNIVERSE_SHARPE: { zh: "子股票池 Sharpe 偏低", en: "low sub-universe Sharpe" },
};

function checkLabel(c: string, zh: boolean): string {
  const m = CHECK_LABELS[c.toUpperCase()];
  return m ? (zh ? m.zh : m.en) : c;
}

// Why a factor was rejected (failing checks) + whether settings-tuning was tried.
function OutcomeTags({ alpha }: { alpha: BrainAlpha }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const checks = (alpha.fail_checks || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!alpha.retried && checks.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {alpha.retried ? (
        <TmTooltip
          content={
            zh
              ? "对该因子做过一次参数自适应重试(调 decay / universe / truncation)"
              : "a settings-adaptation retry was run for this factor"
          }
        >
          <span className="rounded-sm border border-tm-info/60 px-1.5 py-px font-tm-mono text-xs font-bold uppercase text-tm-info">
            {zh ? "已调参重试" : "retried"}
          </span>
        </TmTooltip>
      ) : null}
      {checks.map((c) => (
        <TmTooltip key={c} content={zh ? "未通过的在样内检查" : "failed in-sample check"}>
          <span className="rounded-sm border border-tm-warn/60 px-1.5 py-px font-tm-mono text-xs font-bold uppercase text-tm-warn">
            {checkLabel(c, zh)}
          </span>
        </TmTooltip>
      ))}
    </div>
  );
}

// BRAIN alpha id, shown inline on the row so the user can find the factor back on
// the WorldQuant platform without expanding. Click copies it (stopPropagation so it
// doesn't toggle the row). Only simulated candidates carry one.
function AlphaIdChip({ alphaId }: { alphaId: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [copied, setCopied] = useState(false);
  const resetCopy = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (resetCopy.current != null) clearTimeout(resetCopy.current);
  }, []);
  return (
    <TmButton
      variant="ghost"
      size="xs"
      aria-label={zh ? `复制 Alpha ID ${alphaId}` : `Copy Alpha ID ${alphaId}`}
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(alphaId).then(
          () => {
            setCopied(true);
            if (resetCopy.current != null) clearTimeout(resetCopy.current);
            resetCopy.current = setTimeout(() => setCopied(false), 1200);
          },
          () => undefined,
        );
      }}
      className="border border-tm-rule text-xs tabular-nums hover:border-tm-accent/60 hover:text-tm-accent"
    >
      <Clipboard className="h-3 w-3" aria-hidden />
      <span className="grid">
        <span className={`col-start-1 row-start-1 ${copied ? "invisible" : ""}`}>{alphaId}</span>
        <span className={`col-start-1 row-start-1 ${copied ? "" : "invisible"}`}>{zh ? "已复制" : "Copied"}</span>
      </span>
      <span role="status" className="sr-only">{copied ? (zh ? "已复制" : "Copied") : ""}</span>
    </TmButton>
  );
}

// ── segmented per-candidate progress bar ─────────────────────────────────────
function ProgressSegments({ filled, total }: { filled: number; total: number }) {
  // Cap the segment count so a large n stays legible; each cell is one candidate.
  const segs = Math.max(1, total);
  return (
    <div
      className="flex gap-0.5"
      role="progressbar"
      aria-valuenow={filled}
      aria-valuemin={0}
      aria-valuemax={segs}
    >
      {Array.from({ length: segs }).map((_, i) => (
        <div
          key={i}
          className={`h-2 flex-1 rounded-[1px] transition-colors ${
            i < filled ? "bg-tm-accent" : "bg-tm-rule"
          }`}
        />
      ))}
    </div>
  );
}

// ── manual mining trigger + live tracker (dispatches the GitHub Actions round) ─
function MineButton({
  onStarted,
  onComplete,
  selectedRun,
}: {
  onStarted?: (runId: number | null) => void;
  onComplete?: (runId: number | null) => void;
  selectedRun?: BrainMiningRun | null;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [n, setN] = useState("12");
  const [generationTarget, setGenerationTarget] = useState("24");
  const [family, setFamily] = useState("options");
  const [parentRunId, setParentRunId] = useState<number | null>(null);
  const [state, setState] = useState<"idle" | "sending" | "error">("idle");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [doneMsg, setDoneMsg] = useState<string | null>(null);

  const [job, setJob] = useState<ActiveJob | null>(null);
  const [mined, setMined] = useState(0);
  const [status, setStatus] = useState<{ running: boolean | null } | null>(null);

  // Resume tracking any in-flight round after a refresh / navigation.
  useEffect(() => {
    setJob(loadActiveJob());
  }, []);
  useEffect(() => {
    saveActiveJob(job);
  }, [job]);

  const finish = useCallback(
    (
      completedJob?: ActiveJob | null,
      result: "completed" | "failed" | "stopped" = "completed",
      detail?: string | null,
    ) => {
      const runId = completedJob?.runId ?? null;
      setJob(null);
      setStatus(null);
      if (result === "failed") {
        setState("error");
        setDoneMsg(null);
        setErrMsg(
          detail ||
            (zh
              ? "本轮挖矿失败，请在运行账本查看原因"
              : "mining run failed; inspect the run ledger"),
        );
      } else if (result === "stopped") {
        setState("idle");
        setDoneMsg(
          zh
            ? "已停止本页跟踪，后台任务不受影响"
            : "page tracking stopped; the remote run continues",
        );
      } else {
        setState("idle");
        setDoneMsg(
          zh ? "本轮挖矿完成，结果已刷新" : "mining round complete, results refreshed",
        );
      }
      onComplete?.(runId);
    },
    [onComplete, zh],
  );

  // Poll the round's progress while a job is active.
  useEffect(() => {
    if (!job) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick(current: ActiveJob) {
      try {
        const s = await fetchMineStatus(current.startedAt, current.runId);
        if (!alive) return;
        setStatus({ running: s.running });
        setMined(s.mined);
        if (s.run?.status === "failed") {
          finish(current, "failed", s.run.error_detail);
          return;
        }
        const elapsed = Date.now() - current.dispatchedAt;
        const done =
          // GH says nothing is queued/running (past the startup grace) → done.
          (s.running === false && elapsed > GRACE_MS) ||
          // GH unavailable → fall back to the raw count reaching the target.
          (s.running === null && s.mined >= current.n) ||
          // The ledger is authoritative when this UI has a run id.
          s.run?.status === "completed";
        if (done) {
          finish(current);
          return;
        }
        if (elapsed > MAX_TRACK_MS) {
          finish(current, "stopped");
          return;
        }
      } catch {
        if (alive && Date.now() - current.dispatchedAt > MAX_TRACK_MS) {
          finish(current, "stopped");
          return;
        }
      }
      if (alive) timer = setTimeout(() => void tick(current), POLL_MS);
    }

    void tick(job);
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [job, finish]);

  async function go() {
    setState("sending");
    setErrMsg(null);
    setDoneMsg(null);
    try {
      const nc = Math.max(1, Math.min(30, Number(n) || 12));
      const poolSize = Math.max(
        nc,
        Math.min(60, Number(generationTarget) || nc * 2),
      );
      const r = await triggerMining({
        nCandidates: nc,
        generationTarget: poolSize,
        familyFocus: family,
        parentRunId,
      });
      setMined(0);
      setStatus(null);
      const runId = typeof r.run_id === "number" ? r.run_id : null;
      setJob({
        startedAt: r.started_at,
        n: r.n_candidates,
        generationTarget: r.generation_target_n ?? poolSize,
        dispatchedAt: Date.now(),
        runId,
      });
      onStarted?.(runId);
      setState("idle");
    } catch (e) {
      setState("error");
      setErrMsg(e instanceof Error ? e.message : String(e));
    }
  }

  function reuseSelectedRun() {
    if (!selectedRun) return;
    const budget = Math.max(1, Number(selectedRun.requested_n) || 12);
    setN(String(budget));
    setGenerationTarget(
      String(Math.max(budget, Number(selectedRun.generation_target_n) || budget * 2)),
    );
    setFamily(selectedRun.family_focus || "");
    setParentRunId(selectedRun.id);
    setDoneMsg(
      zh
        ? `已载入 RUN #${selectedRun.id}，确认后可发起独立重跑`
        : `RUN #${selectedRun.id} loaded; review before starting a new run`,
    );
  }

  // Active round: show the live segmented progress + a guard against re-dispatch.
  if (job) {
    const filled = Math.min(mined, job.n);
    const phase =
      status?.running === true
        ? zh
          ? "仿真中"
          : "simulating"
        : status?.running === false
          ? zh
            ? "收尾中"
            : "finishing"
          : zh
            ? "已派发"
            : "dispatched";
    return (
      <div className="flex flex-col gap-2 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-tm-accent" strokeWidth={1.75} />
          <span className="font-tm-mono text-xs text-tm-fg-2">
            {zh ? "挖矿进行中" : "mining in progress"} · {phase}
          </span>
          <span className="font-tm-mono text-xs tabular-nums text-tm-accent">
            {filled} / {job.n}
          </span>
          <TmButton
            onClick={() => finish(job, "stopped")}
            variant="ghost"
            size="xs"
            className="ml-auto"
          >
            {zh ? "停止跟踪" : "stop tracking"}
          </TmButton>
        </div>
        <ProgressSegments filled={filled} total={job.n} />
        <span className="font-tm-mono text-xs text-tm-muted">
          {zh
            ? `生成池 ${job.generationTarget ?? job.n} 个表达式，最多执行 ${job.n} 次真实仿真 · 可离开本页，回来会继续跟踪`
            : `${job.generationTarget ?? job.n} generated expressions, at most ${job.n} real simulations · safe to leave`}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-end gap-x-3 gap-y-2 px-3 py-3">
      <div className="w-32">
        <TmInput
          label={zh ? "仿真预算" : "Simulation budget"}
          value={n}
          onChange={setN}
          inputMode="numeric"
          aria-label={zh ? "真实仿真预算" : "Real simulation budget"}
          fieldSize="sm"
          inputClassName="text-center tabular-nums"
        />
      </div>
      <div className="w-32">
        <TmInput
          label={zh ? "生成池" : "Generation pool"}
          value={generationTarget}
          onChange={setGenerationTarget}
          inputMode="numeric"
          aria-label={zh ? "候选表达式生成池" : "Generated expression pool"}
          fieldSize="sm"
          inputClassName="text-center tabular-nums"
        />
      </div>
      <div className="flex min-w-36 flex-col gap-1">
        <span className="text-xs font-semibold uppercase tracking-[0.06em] text-tm-muted">
          {zh ? "因子家族" : "alpha family"}
        </span>
        <FamilySelect value={family} onChange={setFamily} zh={zh} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {selectedRun ? (
          <TmButton onClick={reuseSelectedRun} variant="secondary" size="sm">
            {zh ? `载入 #${selectedRun.id} 参数` : `Load #${selectedRun.id} settings`}
          </TmButton>
        ) : null}
        <TmButton
          onClick={go}
          loading={state === "sending"}
          loadingLabel={zh ? "派发中" : "dispatching"}
          variant="primary"
          size="sm"
        >
          <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
          {zh ? "开始挖矿" : "Start mining"}
        </TmButton>
      </div>
      <div className="min-w-0 max-w-lg self-end pb-1 text-xs leading-4">
        {state === "error" && errMsg ? (
          <details className="font-tm-mono text-tm-neg">
            <summary className="cursor-pointer">{zh ? "挖矿未能完成，查看错误" : "Mining did not complete. View error."}</summary>
            <p className="mt-1 [overflow-wrap:anywhere]">{errMsg}</p>
          </details>
        ) : doneMsg ? (
          <span className="inline-flex items-start gap-1.5 font-tm-mono text-tm-pos">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            {doneMsg}
          </span>
        ) : (
          <span className="font-tm-mono text-tm-muted">
            {zh
              ? parentRunId != null
                ? `将作为 RUN #${parentRunId} 的独立衍生轮次，原结果不会被覆盖`
                : "生成池先筛选，入选候选才占用仿真预算"
              : parentRunId != null
                ? `new child of RUN #${parentRunId}; original results stay unchanged`
                : "Only shortlisted candidates use the simulation budget."}
          </span>
        )}
      </div>
    </div>
  );
}

// ── main panel ───────────────────────────────────────────────────────────────
const OUTCOMES: Array<BrainOutcome | ""> = ["", "passed", "flagged", "rejected", "sim_error"];
const SORTS = ["created_at", "sharpe", "fitness", "turnover"] as const;

// Outcome filter. A native <select> was invisible on Safari (its value text is
// painted with system form colors that vanish on the theme-forced dark bg, and
// appearance-none didn't cure it). This custom dropdown is plain button/span
// elements that honor `color` in every browser + both LT/DK themes.
function OutcomeSelect({
  value,
  onChange,
  zh,
}: {
  value: BrainOutcome | "";
  onChange: (v: BrainOutcome | "") => void;
  zh: boolean;
}) {
  const labelOf = (o: BrainOutcome | "") =>
    o ? outcomeLabel(o, zh) : zh ? "全部状态" : "all";

  return (
    <TmSelectMenu
      value={value}
      onChange={(next) => onChange(next as BrainOutcome | "")}
      ariaLabel={zh ? "按仿真结论筛选" : "Filter by simulation outcome"}
      size="xs"
      buttonClassName="min-w-[92px]"
      options={OUTCOMES.map((outcome) => ({ value: outcome, label: labelOf(outcome) }))}
    />
  );
}

// Family filter for the results table (distinct from FamilySelect, which picks
// the mining round's family). Includes 'value'/'other' (not mining options) and
// an all-families default. Custom button/span dropdown (native <select> invisible
// on Safari, see OutcomeSelect).
const FAMILY_FILTER_KEYS = ["", "value", "options", "iv_skew_dynamics", "iv_momentum", "iv_term", "vrp", "pcr_dynamics", "option_breakeven", "lowvol", "sentiment", "momentum", "score", "revision", "dispersion", "microstructure", "seasonality", "overnight", "quality", "other"];
function FamilyFilterSelect({
  value,
  onChange,
  zh,
}: {
  value: string;
  onChange: (v: string) => void;
  zh: boolean;
}) {
  const labelOf = (v: string) =>
    v ? familyLabel(v, zh) : zh ? "全部家族" : "all families";
  return (
    <TmSelectMenu
      value={value}
      onChange={onChange}
      ariaLabel={zh ? "按家族筛选结果" : "Filter results by family"}
      size="xs"
      buttonClassName="min-w-[104px]"
      menuMinWidth={160}
      options={FAMILY_FILTER_KEYS.map((family) => ({ value: family, label: labelOf(family) }))}
    />
  );
}

const FAMILIES: Array<[string, string, string]> = [
  ["", "普通(混合)", "normal"],
  ["options", "期权多机制", "options multi-mechanism"],
  ["lowvol", "低波动", "low-vol"],
  ["sentiment", "情绪", "sentiment"],
  ["momentum", "动量", "momentum"],
  ["score", "因子评分", "factor-score"],
  ["revision", "预期修正", "revision"],
  ["dispersion", "分歧度", "dispersion"],
  // Research-derived structural motifs (pv-corr / seasonality / overnight /
  // iv-term / vrp / quality...): one focus value cycling ~11 mechanisms.
  ["frontier", "前沿结构", "frontier"],
  ["composite", "跨机制复合", "composite"],
  ["blend", "拼接(passer×近失)", "blend"],
];

// Native <select> is invisible on Safari (see OutcomeSelect) — same custom
// button/span dropdown so the family label is readable in every browser + theme.
function FamilySelect({
  value,
  onChange,
  zh,
}: {
  value: string;
  onChange: (v: string) => void;
  zh: boolean;
}) {
  const labelOf = (v: string) => {
    const f = FAMILIES.find((x) => x[0] === v) ?? FAMILIES[0];
    return zh ? f[1] : f[2];
  };
  return (
    <TmSelectMenu
      value={value}
      onChange={onChange}
      ariaLabel={zh ? "选择挖矿家族" : "Select mining family"}
      size="sm"
      buttonClassName="min-w-[120px]"
      menuMinWidth={180}
      options={FAMILIES.map(([family, zhLabel, enLabel]) => ({
        value: family,
        label: zh ? zhLabel : enLabel,
      }))}
      placeholder={labelOf(value)}
    />
  );
}

const RECENT_RUN_LIMIT = 8;
type RunCountKey =
  | "requested_n"
  | "generated_n"
  | "screened_n"
  | "simulated_n"
  | "persisted_n"
  | "passed_n"
  | "flagged_n"
  | "rejected_n"
  | "sim_error_n";

function runTime(run: BrainMiningRun): number {
  const value = run.created_at ?? run.started_at ?? run.finished_at;
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function sortRecentRuns(runs: BrainMiningRun[]): BrainMiningRun[] {
  return [...runs].sort((a, b) => runTime(b) - runTime(a) || b.id - a.id);
}

function isManualRun(run: BrainMiningRun): boolean {
  return (run.source ?? "").toLowerCase().includes("manual");
}

function isEmptyCompletedRun(run: BrainMiningRun): boolean {
  const status = (run.status ?? "").toLowerCase();
  return (
    (status === "completed" || status === "complete") &&
    (run.requested_n ?? 0) > 0 &&
    run.generated_n === 0 &&
    run.persisted_n === 0
  );
}

function runSourceLabel(run: BrainMiningRun, zh: boolean): string {
  const source = (run.source ?? "").toLowerCase();
  if (source.includes("manual")) return zh ? "手动" : "manual";
  if (source.includes("sched") || source.includes("cron") || source.includes("daily")) {
    return zh ? "定时" : "scheduled";
  }
  return run.source || (zh ? "历史" : "legacy");
}

function runStatusLabel(run: BrainMiningRun, zh: boolean): string {
  if (isEmptyCompletedRun(run)) return zh ? "失败" : "failed";
  const raw = (run.status ?? run.screen_status ?? "").toLowerCase();
  const labels: Record<string, [string, string]> = {
    queued: ["排队中", "queued"],
    running: ["运行中", "running"],
    started: ["运行中", "started"],
    screening: ["筛选中", "screening"],
    fallback: ["规则筛选", "deterministic screen"],
    fallback_partial: ["规则筛选，证据不完整", "deterministic screen, partial evidence"],
    timeout: ["筛选超时", "screen timeout"],
    completed: ["已完成", "completed"],
    complete: ["已完成", "complete"],
    failed: ["失败", "failed"],
    error: ["错误", "error"],
  };
  const label = labels[raw];
  return label ? (zh ? label[0] : label[1]) : run.status || run.screen_status || (zh ? "未知" : "unknown");
}

function runStatusClass(run: BrainMiningRun): string {
  if (isEmptyCompletedRun(run)) return "text-tm-neg";
  const raw = (run.status ?? run.screen_status ?? "").toLowerCase();
  if (raw.includes("fail") || raw.includes("error")) return "text-tm-neg";
  if (raw.includes("run") || raw.includes("queue") || raw.includes("screen")) return "text-tm-accent";
  if (raw.includes("complete") || raw.includes("pass")) return "text-tm-pos";
  return "text-tm-muted";
}

function screenStatusLabel(status: string | null | undefined, zh: boolean): string {
  const raw = (status ?? "").toLowerCase();
  const labels: Record<string, [string, string]> = {
    completed: ["LLM 评分完成", "LLM screen complete"],
    partial: ["LLM 部分评分，规则补位", "partial LLM screen with fallback"],
    timeout: ["LLM 超时，规则补位", "LLM timeout with fallback"],
    error: ["LLM 错误，规则补位", "LLM error with fallback"],
    fallback: ["规则证据筛选", "deterministic evidence screen"],
    fallback_partial: ["规则筛选，证据不完整", "deterministic screen, partial evidence"],
    bypassed: ["LLM 未配置", "LLM not configured"],
    failed: ["筛选失败", "screen failed"],
  };
  const label = labels[raw];
  return label ? label[zh ? 0 : 1] : status || (zh ? "未知" : "unknown");
}

function runCount(run: BrainMiningRun | null, key: RunCountKey): string {
  const value = run?.[key];
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "—";
}

function runRate(numerator: number | null | undefined, denominator: number | null | undefined): string {
  if (typeof numerator !== "number" || typeof denominator !== "number" || denominator <= 0) {
    return "—";
  }
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function runNextStep(run: BrainMiningRun, zh: boolean): string {
  const simulated = run.simulated_n ?? 0;
  const passed = run.passed_n ?? 0;
  const flagged = run.flagged_n ?? 0;
  const rejected = run.rejected_n ?? 0;
  const simErrors = run.sim_error_n ?? 0;
  const generated = run.generated_n ?? 0;
  const screened = run.screened_n ?? 0;
  const requested = run.requested_n ?? 0;

  if (["failed", "error"].includes((run.status ?? "").toLowerCase()) || isEmptyCompletedRun(run)) {
    return runFailureAction(run, zh);
  }
  if (simulated > 0 && simErrors / simulated >= 0.2) {
    return zh ? "仿真错误偏高，先检查 BRAIN 会话、表达式格式或上游限流。" : "Simulation errors are elevated; inspect auth, expressions, or upstream throttling.";
  }
  if (run.screen_status === "failed") {
    return zh ? "Logic screen 本轮失败并已旁路，先检查模型配置，再决定是否复用本轮。" : "The logic screen failed and was bypassed; inspect model configuration before reuse.";
  }
  if (run.screen_status === "bypassed") {
    return zh ? "Logic screen 未配置，系统直接使用仿真预算；扩大生成池暂不会提高筛选质量。" : "No logic screen was configured; widening generation will not improve ranking yet.";
  }
  if (run.status === "completed" && screened < requested && generated > 0) {
    const technicalFallback = ["partial", "timeout", "error"].includes(run.screen_status ?? "") ||
      /logic model unavailable|timed out|logic screen failed/i.test(run.screen_detail ?? "");
    if (technicalFallback) {
      const simulationState = simulated > 0
        ? zh ? `本轮已有 ${simulated} 条完成 BRAIN 仿真。` : `${simulated} candidates completed BRAIN simulation.`
        : zh ? "本轮尚未执行 BRAIN 仿真。" : "BRAIN simulation has not run.";
      return zh
        ? `LLM 预筛没有完整完成；已返回评分继续有效，未评分候选仍进入规则证据筛选。${simulationState}打开“候选审计”查看逐条状态。`
        : `The LLM screen did not fully complete; returned scores remain valid and unscored candidates still enter the evidence screen. ${simulationState} Open Candidate Audit for per-candidate state.`;
    }
    return zh
      ? `证据筛选保留了 ${requested - screened} 个仿真名额，低可信候选没有被回填消耗预算。打开“候选审计”查看逐条字段覆盖与阻断原因。`
      : `The evidence screen kept ${requested - screened} simulation slots unused instead of backfilling weak candidates. Open Candidate Audit for field coverage and blocking reasons.`;
  }
  if (passed === 0 && rejected > 0) {
    return zh ? "主要损失发生在硬门槛，优先换家族或扩大生成池，不要盲目增加仿真数。" : "Hard gates dominate; change family or widen generation before buying more simulations.";
  }
  if (flagged > passed) {
    return zh ? "相关性或家族饱和较重，下一轮优先换正交家族；已有 passer 时可尝试 blend。" : "Correlation or family saturation dominates; rotate family, or try blend with passers.";
  }
  if (passed > 0) {
    return zh ? "先审阅通过项的 PnL、自相关与年度稳定性，再人工提交；不要自动晋级。" : "Review PnL, self-correlation, and yearly stability before manual submission.";
  }
  if (generated > 0 && generated <= requested && run.status === "completed") {
    return zh ? "生成池没有形成候选冗余，下一轮可扩大到仿真预算的约 2 倍。" : "The pool had no ranking headroom; try roughly 2× the simulation budget.";
  }
  return zh ? "等待本轮完成后再判断瓶颈。" : "Wait for completion before diagnosing the bottleneck.";
}

function RunSelector({
  runs,
  disabled,
  selectedRunId,
  onChange,
  zh,
}: {
  runs: BrainMiningRun[];
  disabled: boolean;
  selectedRunId: number | null;
  onChange: (id: number | null) => void;
  zh: boolean;
}) {
  const selected = runs.find((run) => run.id === selectedRunId) ?? null;
  const buttonLabel = selected
    ? `RUN #${selected.id}`
    : selectedRunId != null
      ? `RUN #${selectedRunId}`
      : zh
        ? "全部结果"
        : "all results";

  return (
    <TmSelectMenu
      disabled={disabled}
      value={selectedRunId == null ? "" : String(selectedRunId)}
      onChange={(next) => onChange(next ? Number(next) : null)}
      ariaLabel={zh ? "选择挖矿运行" : "Select mining run"}
      size="sm"
      buttonClassName="min-w-[150px]"
      menuMinWidth={270}
      placeholder={buttonLabel}
      options={[
        {
          value: "",
          label: zh ? "历史兼容视图 · 全部结果" : "legacy view · all results",
          meta: "ALL",
        },
        ...runs.map((run) => ({
          value: String(run.id),
          label: `RUN #${run.id} · ${runSourceLabel(run, zh)}`,
          meta: `${familyLabel(run.family_focus, zh)} · ${fmtUtc8(run.created_at ?? run.started_at)} · ${runStatusLabel(run, zh)}`,
        })),
      ]}
    />
  );
}

function RunLedger({
  run,
  selectedRunId,
  runsError,
  runsLoading,
  runsTotal,
  zh,
}: {
  run: BrainMiningRun | null;
  selectedRunId: number | null;
  runsError: string | null;
  runsLoading: boolean;
  runsTotal: number;
  zh: boolean;
}) {
  if (!run) {
    return (
      <div className="border-b border-tm-rule px-3 py-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-xs text-tm-muted">
          {runsLoading ? (
            <span>{zh ? "正在读取运行记录…" : "Loading runs…"}</span>
          ) : selectedRunId != null ? (
            <span>{zh ? `RUN #${selectedRunId} 等待账本记录` : `RUN #${selectedRunId} awaiting ledger record`}</span>
          ) : runsError ? (
            <span>{zh ? "运行选择器暂不可用，显示兼容的全部结果" : "run selector unavailable; showing legacy all-results mode"}</span>
          ) : runsTotal > 0 ? (
            <span>{zh ? "历史兼容视图，结果可能跨多个运行" : "legacy all-results view; rows may span runs"}</span>
          ) : (
            <span>{zh ? "暂无运行记录" : "no mining runs yet"}</span>
          )}
        </div>
        {runsError ? (
          <details className="mt-1 font-tm-mono text-xs text-tm-warn">
            <summary className="cursor-pointer">{zh ? "运行记录读取失败，可刷新重试" : "Could not load runs. Refresh to retry."}</summary>
            <p className="mt-1 [overflow-wrap:anywhere]">{runsError}</p>
          </details>
        ) : null}
      </div>
    );
  }

  const funnel: Array<[string, string]> = [
    [
      zh ? "生成" : "generated",
      `${runCount(run, "generated_n")} / ${run.generation_target_n ?? "—"}`,
    ],
    [zh ? "入选仿真" : "selected", runCount(run, "screened_n")],
    [zh ? "已仿真 / 预算" : "Simulated / budget", `${runCount(run, "simulated_n")} / ${runCount(run, "requested_n")}`],
    [zh ? "已入库" : "persisted", runCount(run, "persisted_n")],
  ];
  const outcome = [
    [zh ? "通过" : "passed", runCount(run, "passed_n"), "text-tm-pos"],
    [zh ? "存疑" : "flagged", runCount(run, "flagged_n"), "text-tm-warn"],
    [zh ? "淘汰" : "rejected", runCount(run, "rejected_n"), "text-tm-muted"],
    [zh ? "仿真错误" : "sim errors", runCount(run, "sim_error_n"), "text-tm-neg"],
  ] as const;

  return (
    <div className="space-y-2 border-b border-tm-rule px-3 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-xs">
        <span className="text-tm-fg-2">{runSourceLabel(run, zh)}</span>
        <span className="text-tm-muted">{familyLabel(run.family_focus, zh)}</span>
        {run.parent_run_id != null ? (
          <span className="text-tm-info">{zh ? `源 RUN #${run.parent_run_id}` : `from RUN #${run.parent_run_id}`}</span>
        ) : null}
        <span className={runStatusClass(run)}>{runStatusLabel(run, zh)}</span>
        <span className="text-tm-muted">{fmtUtc8(run.created_at ?? run.started_at)} UTC+8</span>
        {runsTotal > 0 ? <span className="ml-auto text-tm-muted">{runsTotal} {zh ? "轮" : "runs"}</span> : null}
      </div>
      <dl className="grid grid-cols-2 divide-tm-rule border border-tm-rule bg-tm-bg-2 sm:grid-cols-4 sm:divide-x">
        {funnel.map(([label, value]) => (
          <div key={label} className="flex min-w-0 items-baseline gap-2 px-3 py-1.5 font-tm-mono">
            <dt className="text-xs text-tm-muted">{label}</dt>
            <dd className="ml-auto shrink-0 text-sm tabular-nums text-tm-fg">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-xs">
        {outcome.map(([label, count, className]) => (
          <span key={label} className={className}>{label} {count}</span>
        ))}
        {run.screen_status ? (
          <span className={["failed", "timeout", "error", "partial", "fallback_partial", "bypassed"].includes(run.screen_status.toLowerCase()) ? "text-tm-warn" : "text-tm-muted"}>
            {screenStatusLabel(run.screen_status, zh)}
          </span>
        ) : null}
      </div>
      <p className={`text-xs leading-relaxed ${isEmptyCompletedRun(run) || ["failed", "error"].includes((run.status ?? "").toLowerCase()) ? "text-tm-neg" : "text-tm-fg-2"}`}>
        {runNextStep(run, zh)}
      </p>
      <details key={run.id} className="font-tm-mono text-xs text-tm-muted">
        <summary className="w-fit cursor-pointer focus-visible:outline focus-visible:outline-tm-accent">
          {zh ? "运行诊断" : "Run diagnostics"}
        </summary>
        <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {[
          [zh ? "筛选利用" : "screen use", runRate(run.screened_n, run.generated_n)],
          [zh ? "通过率" : "pass yield", runRate(run.passed_n, run.simulated_n)],
          [zh ? "仿真错误" : "sim errors", runRate(run.sim_error_n, run.simulated_n)],
        ].map(([label, value]) => (
          <div key={label} className="flex gap-2">
            <dt>{label}</dt>
            <dd className="tabular-nums text-tm-fg">{value}</dd>
          </div>
        ))}
        </dl>
        {run.error_detail ? <p className="mt-2 whitespace-pre-wrap text-tm-neg [overflow-wrap:anywhere]">{run.error_detail}</p> : null}
        {run.screen_detail ? <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{run.screen_detail}</p> : null}
      </details>
    </div>
  );
}


export function BrainMiningPanel() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_BRAIN_PAGE_SIZE);
  const [outcome, setOutcome] = useState<BrainOutcome | "">("");
  const [q, setQ] = useState("");
  const [sharpeMin, setSharpeMin] = useState("");
  const [familyFilter, setFamilyFilter] = useState("");
  const [sort, setSort] = useState<string>("created_at");
  const [descending, setDescending] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [viewChoice, setViewChoice] = useState<{ runId: number | null; view: WorkbenchView } | null>(null);

  const [response, setResponse] = useState<{
    query: BrainAlphaQuery;
    data: { alphas: BrainAlpha[]; total: number } | null;
    error: string | null;
  } | null>(null);
  const [resultsLoading, setResultsLoading] = useState(true);
  const [runs, setRuns] = useState<BrainMiningRun[] | null>(null);
  const [runsPage, setRunsPage] = useState(1);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runsLoading, setRunsLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(
    () => loadActiveJob()?.runId ?? null,
  );
  // A run chosen by the user or by a just-dispatched manual job must not be
  // replaced by a later refresh's default selection.
  const selectionTouched = useRef(selectedRunId != null);

  const runLoadSequence = useRef(0);
  const loadRuns = useCallback(async () => {
    const sequence = ++runLoadSequence.current;
    setRunsLoading(true);
    setRuns(null);
    try {
      const res = await fetchBrainRuns(RECENT_RUN_LIMIT, undefined, (runsPage - 1) * RECENT_RUN_LIMIT);
      if (sequence !== runLoadSequence.current) return;
      const recent = sortRecentRuns(Array.isArray(res.runs) ? res.runs : []).slice(0, RECENT_RUN_LIMIT);
      setRuns(recent);
      setRunsTotal(typeof res.total === "number" ? res.total : recent.length);
      setRunsError(null);
      if (!selectionTouched.current) {
        const preferred = (runsPage === 1 ? recent.find(isManualRun) : null) ?? recent[0] ?? null;
        setSelectedRunId(preferred?.id ?? null);
      }
    } catch (e) {
      // The ledger is a rollout-era enhancement. Keep the legacy all-results
      // query usable when this endpoint is missing or temporarily unavailable.
      if (sequence === runLoadSequence.current) setRunsError(e instanceof Error ? e.message : String(e));
    } finally {
      if (sequence === runLoadSequence.current) setRunsLoading(false);
    }
  }, [runsPage]);

  const query = useMemo<BrainAlphaQuery>(
    () => ({
      limit: pageSize,
      offset: page * pageSize,
      run_id: selectedRunId ?? undefined,
      outcome: outcome || undefined,
      q: q.trim() || undefined,
      sharpe_min: sharpeMin ? Number(sharpeMin) : undefined,
      family: familyFilter || undefined,
      sort,
      descending,
    }),
    [page, pageSize, selectedRunId, outcome, q, sharpeMin, familyFilter, sort, descending],
  );

  const loadSequence = useRef(0);
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    setResultsLoading(true);
    try {
      const res = await fetchBrainAlphas(query);
      if (sequence !== loadSequence.current) return;
      setResponse({ query, data: res, error: null });
    } catch (e) {
      if (sequence !== loadSequence.current) return;
      setResponse({ query, data: null, error: e instanceof Error ? e.message : String(e) });
    } finally {
      if (sequence === loadSequence.current) setResultsLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const handleRunSelection = useCallback((runId: number | null) => {
    selectionTouched.current = true;
    setSelectedRunId(runId);
    setPage(0);
    setExpanded(null);
    setViewChoice(null);
  }, []);

  const handleMiningStarted = useCallback(
    (runId: number | null) => {
      if (runId == null) return;
      selectionTouched.current = true;
      setSelectedRunId(runId);
      setPage(0);
      setExpanded(null);
      setViewChoice(null);
      if (runsPage !== 1) setRunsPage(1);
      else void loadRuns();
    },
    [loadRuns, runsPage],
  );

  const handleMiningComplete = useCallback(
    (runId: number | null) => {
      if (runId != null) {
        selectionTouched.current = true;
        setSelectedRunId(runId);
        setPage(0);
        setExpanded(null);
        if (selectedRunId === runId && page === 0) void load();
        if (runsPage !== 1) setRunsPage(1);
        else void loadRuns();
      } else {
        // Legacy POST responses do not identify a run. Refresh the current
        // compatibility query without changing the user's selected run.
        void load();
        void loadRuns();
      }
    },
    [load, loadRuns, page, runsPage, selectedRunId],
  );

  // reset to page 0 whenever a filter or the page size changes
  useEffect(() => {
    setPage(0);
    setExpanded(null);
  }, [selectedRunId, outcome, q, sharpeMin, familyFilter, sort, descending, pageSize]);

  function toggle(id: number) {
    setExpanded((prev) => nextExpandedAlpha(prev, id));
  }

  function toggleSort(col: string) {
    if (sort === col) setDescending((d) => !d);
    else {
      setSort(col);
      setDescending(true);
    }
  }

  // A result only belongs under the exact query that produced it.
  const data = response?.query === query ? response.data : null;
  const loadError = response?.query === query ? response.error : null;
  const total = data?.total ?? 0;
  const filtered = Boolean(query.outcome || query.family || query.q || query.sharpe_min != null);
  const refreshing = runsLoading || resultsLoading;
  const selectedRun = runs?.find((run) => run.id === selectedRunId) ?? null;
  const recentRuns = runs ?? [];
  const selectedRunFailed = Boolean(
    selectedRun &&
      ((selectedRun.status ?? "").toLowerCase() === "failed" ||
        (selectedRun.status ?? "").toLowerCase() === "error" ||
        isEmptyCompletedRun(selectedRun)),
  );

  const workbenchView = viewChoice?.runId === selectedRunId
    ? viewChoice.view
    : hasUnsimulatedCandidates(selectedRun) ? "audit" : "results";

  function changeView(view: WorkbenchView) {
    setViewChoice({ runId: selectedRunId, view });
    setExpanded(null);
  }

  return (
    <TmScreen>
      <WorkbenchHeader
        eyebrow={zh ? "高级研究工具 · WorldQuant" : "Advanced research · WorldQuant"}
        title={zh ? "BRAIN 因子挖掘" : "BRAIN Alpha Mining"}
        subtitle={zh ? "候选筛选与官方仿真" : "Candidate screening and official simulation"}
      />
      <TmPane title={zh ? "新建挖矿运行" : "New mining run"}>
        <MineButton
          selectedRun={selectedRun}
          onStarted={handleMiningStarted}
          onComplete={handleMiningComplete}
        />
      </TmPane>

      <TmPane
        title={zh ? "运行回顾" : "Run review"}
        meta={
          <TmButton
            onClick={() => { void loadRuns(); void load(); }}
            loading={refreshing}
            loadingLabel={zh ? "刷新中…" : "Refreshing…"}
            variant="ghost"
            size="xs"
            aria-label={zh ? "刷新运行记录与结果" : "Refresh runs and results"}
          >
            <RefreshCw className="h-3 w-3" strokeWidth={1.75} />
            {zh ? "刷新" : "Refresh"}
          </TmButton>
        }
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
          <span className="font-tm-mono text-xs uppercase tracking-wider text-tm-muted">
            {zh ? "查看运行" : "View run"}
          </span>
          <RunSelector
            runs={recentRuns}
            disabled={runsLoading || Boolean(runsError)}
            selectedRunId={selectedRunId}
            onChange={handleRunSelection}
            zh={zh}
          />
          {runsError && selectedRun ? (
            <span className="font-tm-mono text-xs text-tm-warn">{zh ? "运行记录刷新失败，仍显示上次记录" : "Run refresh failed; showing the last loaded record."}</span>
          ) : null}
        </div>
        {runsTotal > RECENT_RUN_LIMIT && <TmPagination
          page={runsPage} pageSize={RECENT_RUN_LIMIT} totalItems={runsTotal}
          pageSizeOptions={[RECENT_RUN_LIMIT]} onPageChange={(next) => { selectionTouched.current = false; setRunsPage(next); }}
          onPageSizeChange={() => {}} loading={runsLoading}
          labels={{
            navigation: zh ? "运行目录分页" : "Run directory pagination",
            previous: zh ? "较新运行" : "Newer", next: zh ? "更早运行" : "Older",
            previousAriaLabel: zh ? "查看较新运行" : "View newer runs",
            nextAriaLabel: zh ? "查看更早运行" : "View older runs",
            page: (current, count) => `${current} / ${count}`,
            pageSize: zh ? "每页" : "Per page",
            total: (total) => zh ? `共 ${total} 轮 · 翻页载入该页首轮` : `${total} runs · paging opens the first run`,
          }}
        />}
        <RunLedger
          run={selectedRun}
          selectedRunId={selectedRunId}
          runsError={runsError}
          runsLoading={runsLoading}
          runsTotal={runsTotal}
          zh={zh}
        />
        <SegmentedTabs<WorkbenchView>
          items={[
            {
              key: "results",
              label: zh ? "仿真结果" : "simulation results",
              badge: <span className="font-tm-mono text-xs tabular-nums">{selectedRun?.persisted_n ?? (data && !filtered ? total : "—")}</span>,
            },
            {
              key: "audit",
              label: zh ? "候选审计" : "candidate audit",
              badge: <span className="font-tm-mono text-xs tabular-nums">{selectedRun?.generated_n ?? "—"}</span>,
            },
          ]}
          active={workbenchView}
          onChange={changeView}
          ariaLabel={zh ? "BRAIN 挖掘数据视图" : "BRAIN mining data views"}
        />

        {workbenchView === "audit" ? (
          <BrainCandidateAudit
            key={selectedRunId ?? "legacy"}
            runId={selectedRunId}
            generatedCount={selectedRun?.generated_n}
          />
        ) : (
          <>
        {/* filter bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
          <OutcomeSelect value={outcome} onChange={setOutcome} zh={zh} />
          <FamilyFilterSelect value={familyFilter} onChange={setFamilyFilter} zh={zh} />
          <TmInput
            value={q}
            onChange={setQ}
            placeholder={zh ? "搜索表达式或编码…" : "search expr or code…"}
            aria-label={zh ? "搜索表达式或 Alpha ID" : "Search expression or Alpha ID"}
            fieldSize="sm"
            className="w-56"
          />
          <TmInput
            value={sharpeMin}
            onChange={setSharpeMin}
            placeholder={zh ? "Sharpe ≥" : "Sharpe ≥"}
            aria-label={zh ? "最低 Sharpe" : "Minimum Sharpe"}
            inputMode="decimal"
            fieldSize="sm"
            className="w-24"
          />
          <span className="ml-auto font-tm-mono text-xs text-tm-muted">
            {zh ? "排序:" : "sort:"}
          </span>
          {SORTS.map((s) => (
            <TmButton
              key={s}
              onClick={() => toggleSort(s)}
              variant="ghost"
              size="xs"
              aria-pressed={sort === s}
              className={sort === s ? "text-tm-accent" : undefined}
            >
              {s === "created_at" ? (zh ? "时间" : "Date") : s === "turnover" ? (zh ? "换手" : "Turnover") : s === "sharpe" ? "Sharpe" : "Fitness"}
              {sort === s ? (
                descending ? (
                  <ArrowDown className="h-2.5 w-2.5" strokeWidth={2} />
                ) : (
                  <ArrowUp className="h-2.5 w-2.5" strokeWidth={2} />
                )
              ) : null}
            </TmButton>
          ))}
        </div>

        {loadError ? (
          <details className="px-3 py-4 font-tm-mono text-xs text-tm-neg">
            <summary className="cursor-pointer">{zh ? "结果读取失败，可刷新重试" : "Could not load results. Refresh to retry."}</summary>
            <p className="mt-2 [overflow-wrap:anywhere]">{loadError}</p>
          </details>
        ) : data === null ? (
          <p role="status" className="flex items-center gap-2 px-3 py-5 font-tm-mono text-xs text-tm-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />
            {zh ? "正在读取仿真结果…" : "Loading simulation results…"}
          </p>
        ) : data.alphas.length === 0 ? (
          <div className="flex flex-wrap items-center gap-3 px-3 py-5 text-xs text-tm-muted">
            {selectedRunFailed
              ? (zh ? "本轮运行失败，暂无仿真结果。请查看运行诊断。" : "This run failed and has no simulation results. See Run diagnostics.")
              : hasUnsimulatedCandidates(selectedRun)
                ? (zh ? "本轮生成了候选，但没有执行 BRAIN 仿真。" : "This run generated candidates but did not execute BRAIN simulations.")
                : filtered
                  ? (zh ? "没有符合当前筛选的结果。" : "No results match these filters.")
                  : selectedRunId != null
                    ? (zh ? "本轮暂无已入库的仿真结果。" : "No simulation results have been saved for this run.")
                    : (zh ? "暂无仿真结果。连接 BRAIN 账号后即可新建运行。" : "No simulation results yet. Connect a BRAIN account to start a run.")}
            {hasUnsimulatedCandidates(selectedRun) ? (
              <TmButton variant="secondary" size="xs" onClick={() => changeView("audit")}>
                {zh ? "查看候选审计" : "Open candidate audit"}
              </TmButton>
            ) : filtered && !selectedRunFailed ? (
              <TmButton variant="secondary" size="xs" onClick={() => {
                setOutcome(""); setFamilyFilter(""); setQ(""); setSharpeMin("");
              }}>
                {zh ? "清除筛选" : "Clear filters"}
              </TmButton>
            ) : null}
          </div>
        ) : (
          <TmTableFrame aria-busy={resultsLoading}>
            <TmTable
              caption={zh ? "BRAIN 仿真结果" : "BRAIN simulation results"}
              className="min-w-[560px] table-fixed"
            >
              <colgroup>
                <col />
                <col className="w-[64px] sm:w-[80px]" />
                <col className="w-[64px] sm:w-[80px]" />
                <col className="w-[82px] sm:w-[108px]" />
                <col className="w-[65px] sm:w-[82px]" />
                <col className="w-[130px] sm:w-[152px]" />
              </colgroup>
              <TmTableHead>
                <TmTableRow>
                  <TmTableHeaderCell>{zh ? "表达式" : "Expression"}</TmTableHeaderCell>
                  <TmTableHeaderCell textAlign="right">Sharpe</TmTableHeaderCell>
                  <TmTableHeaderCell textAlign="right">Fitness</TmTableHeaderCell>
                  <TmTableHeaderCell textAlign="right">
                    <TmTooltip content={zh ? "与现有 ACTIVE 因子的最大相关性。0.70 为官方门槛。" : "Maximum correlation with ACTIVE alphas. The official limit is 0.70."}>
                      <span className="cursor-help">{zh ? "官方自相关" : "Official S-corr"}</span>
                    </TmTooltip>
                  </TmTableHeaderCell>
                  <TmTableHeaderCell textAlign="right">{zh ? "评级" : "Grade"}</TmTableHeaderCell>
                  <TmTableHeaderCell textAlign="right">{zh ? "结论" : "Verdict"}</TmTableHeaderCell>
                </TmTableRow>
              </TmTableHead>
              <TmTableBody>
                {data.alphas.map((a, i) => {
                  const open = expanded === a.id;
                  const verdict = candidateVerdict(a);
                  const submission = brainSubmissionState(a);
                  const previous = i > 0 ? data.alphas[i - 1] : null;
                  const newBatch = sort === "created_at" && previous != null &&
                    (a.batch_started_at ?? "") !== (previous.batch_started_at ?? "");
                  return (
                    <Fragment key={a.id}>
                      {newBatch ? (
                        <TmTableRow className="border-t border-tm-accent/30">
                          <TmTableCell colSpan={6} className="bg-tm-bg-2 py-1 text-tm-muted">
                            {a.batch_started_at ? `${fmtUtc8(a.batch_started_at)} UTC+8` : (zh ? "其他批次" : "Other batch")}
                          </TmTableCell>
                        </TmTableRow>
                      ) : null}
                      <TmTableRow className={open ? "bg-tm-bg-2" : undefined}>
                        <TmTableRowHeader className="py-1.5">
                          <TmRowButton
                            onClick={() => toggle(a.id)}
                            aria-expanded={open}
                            aria-controls={open ? `brain-alpha-detail-${a.id}` : undefined}
                            className="flex w-full min-w-0 items-start gap-1.5 rounded-sm py-0.5 text-left"
                          >
                            {open ? (
                              <ChevronDown className="mt-0.5 h-3 w-3 shrink-0 text-tm-muted" aria-hidden />
                            ) : (
                              <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-tm-muted" aria-hidden />
                            )}
                            <code className={`line-clamp-2 min-w-0 break-all leading-snug ${a.is_blend ? "text-tm-accent" : "text-tm-fg"}`}>
                              {a.expression}
                            </code>
                            {submission === "accepted" ? (
                              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-tm-pos" aria-label={zh ? "BRAIN 已受理" : "Accepted by BRAIN"} />
                            ) : null}
                          </TmRowButton>
                          {a.family || a.alpha_id ? (
                            <div className="ml-[18px] mt-1 flex flex-wrap items-center gap-2">
                              <FamilyBadge family={a.family} active={familyFilter === a.family} onClick={(fam) =>
                                setFamilyFilter((cur) => (cur === fam ? "" : fam))
                              } />
                              {a.alpha_id ? <AlphaIdChip alphaId={a.alpha_id} /> : null}
                            </div>
                          ) : null}
                        </TmTableRowHeader>
                        <TmTableCell textAlign="right" numeric>{fmt(a.sharpe)}</TmTableCell>
                        <TmTableCell textAlign="right" numeric>{fmt(a.fitness)}</TmTableCell>
                        <TmTableCell textAlign="right" numeric><OfficialSCorrCell alpha={a} zh={zh} /></TmTableCell>
                        <TmTableCell textAlign="right"><GradeBadge grade={a.grade} /></TmTableCell>
                        <TmTableCell textAlign="right">
                          <TmTooltip content={zh ? "展开表达式查看依据" : "Expand expression for details"}>
                            <span className={`inline-block border px-1.5 py-px text-xs font-bold ${verdict.cls}`}>
                              {zh ? verdict.labelZh : verdict.labelEn}
                            </span>
                          </TmTooltip>
                        </TmTableCell>
                      </TmTableRow>
                      {open ? (
                        <TmTableRow id={`brain-alpha-detail-${a.id}`}>
                          <TmTableCell colSpan={6} className="p-0">
                            <RowDetail alpha={a} onDone={() => void load()} />
                          </TmTableCell>
                        </TmTableRow>
                      ) : null}
                    </Fragment>
                  );
                })}
              </TmTableBody>
            </TmTable>
          </TmTableFrame>
        )}

        {/* Canonical workstation pagination. */}
        {total > 0 ? (
          <TmPagination
            page={page + 1}
            pageSize={pageSize}
            totalItems={total}
            pageSizeOptions={[10, 20, 50, 100, 200]}
            labels={{
              navigation: zh ? "BRAIN 因子结果分页" : "BRAIN alpha result pagination",
              previous: zh ? "上一页" : "Previous",
              previousAriaLabel: zh ? "上一页" : "Previous page",
              next: zh ? "下一页" : "Next",
              nextAriaLabel: zh ? "下一页" : "Next page",
              page: (currentPage, totalPages) =>
                zh
                  ? `第 ${currentPage} / ${totalPages} 页`
                  : `Page ${currentPage} / ${totalPages}`,
              pageSize: zh ? "每页" : "Rows",
              total: (count) => (zh ? `共 ${count} 条` : `${count} total`),
            }}
            onPageChange={(nextPage) => {
              setPage(nextPage - 1);
              setExpanded(null);
            }}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize);
              setExpanded(null);
            }}
          />
        ) : null}
          </>
        )}
      </TmPane>
    </TmScreen>
  );
}
