"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Loader2,
  Send,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import { BrainPnLChart, type ChartKind } from "@/components/brain/BrainPnLChart";
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

const DEFAULT_PAGE_SIZE = 20;

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
    : { passed: "PASS", flagged: "FLAG", rejected: "OUT", sim_error: "ERR" }[o];
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
type SubmitState = "idle" | "confirm" | "sending" | "done" | "error";

function SubmitControl({ alpha, onDone }: { alpha: BrainAlpha; onDone: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [state, setState] = useState<SubmitState>(
    alpha.submitted_at ? "done" : "idle",
  );
  const [msg, setMsg] = useState<string | null>(alpha.brain_status);

  if (state === "done") {
    return (
      <span className="inline-flex items-center gap-1.5 font-tm-mono text-[11px] text-tm-pos">
        <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
        {zh ? "已提交" : "submitted"}
        {msg ? ` · ${msg}` : ""}
      </span>
    );
  }

  async function doSubmit() {
    setState("sending");
    try {
      const r = await submitBrainAlpha(alpha.id);
      setMsg(r.brain_status);
      setState("done");
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
          <button
            type="button"
            onClick={doSubmit}
            className="inline-flex items-center gap-1.5 rounded border border-tm-accent bg-tm-accent px-2.5 py-1 font-tm-mono text-[11px] font-bold text-tm-bg hover:opacity-90"
          >
            <Send className="h-3 w-3" strokeWidth={2} />
            {zh ? "确认提交" : "Confirm"}
          </button>
          <button
            type="button"
            onClick={() => setState("idle")}
            className="font-tm-mono text-[11px] text-tm-muted hover:text-tm-fg"
          >
            {zh ? "取消" : "cancel"}
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setState("confirm")}
          disabled={state === "sending"}
          className="inline-flex items-center gap-1.5 rounded border border-tm-accent/60 bg-tm-accent/10 px-2.5 py-1 font-tm-mono text-[11px] text-tm-accent transition-opacity hover:bg-tm-accent/20 disabled:opacity-50"
        >
          {state === "sending" ? (
            <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
          ) : (
            <Send className="h-3 w-3" strokeWidth={1.75} />
          )}
          {zh ? "提交到 BRAIN" : "Submit to BRAIN"}
        </button>
      )}
      {state === "error" && msg ? (
        <span className="font-tm-mono text-[10.5px] text-tm-neg">{msg}</span>
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
      <div className="mb-1 font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {zh ? "仿真参数" : "Simulation settings"}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        {cells.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 font-mono text-[10.5px]">
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
        <span className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-accent">
          {zh ? "研究证据" : "Research evidence"}
        </span>
        <span className="font-tm-mono text-[9.5px] text-tm-muted">
          {proxy?.active
            ? `${zh ? "代理已验证" : "proxy validated"} · n=${proxy.sample_n ?? "—"}`
            : zh
              ? "代理未启用，使用分层后验"
              : "proxy inactive; hierarchical posterior used"}
        </span>
      </div>
      <div className="grid gap-3 text-[10.5px] lg:grid-cols-4">
        <div>
          <div className="font-tm-mono text-[9px] uppercase text-tm-muted">
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
          <div className="mt-1 font-tm-mono text-[9.5px] text-tm-muted">
            {hypothesis?.confidence || "—"} · {hypothesis?.target || "—"}
          </div>
          {semantic ? (
            <div
              className={`mt-1 font-tm-mono text-[9.5px] ${alignmentStatus === "aligned" ? "text-tm-pos" : "text-tm-warn"}`}
              title={semantic.target_outcome_alignment?.target}
            >
              {alignmentLabel}
            </div>
          ) : null}
        </div>
        <div>
          <div className="font-tm-mono text-[9px] uppercase text-tm-muted">
            {zh ? "字段可测量性" : "Field measurability"}
          </div>
          <div className="font-tm-mono text-tm-fg">
            {mapping?.dataset_ids?.join(" + ") || "unmapped"}
          </div>
          <div className="mt-1 font-tm-mono text-[9.5px] text-tm-muted">
            coverage {pct(mapping?.coverage)} · mapped {pct(mapping?.mapped_ratio)}
          </div>
          {semantic ? (
            <>
              <div className={`mt-1 font-tm-mono text-[9.5px] ${semanticTone}`}>
                {semanticLabel} · {semantic.matched_required_semantics?.length ?? 0}/{semantic.required_semantics?.length ?? 0}
              </div>
              {semantic.missing_required_semantics?.length ? (
                <div
                  className="mt-1 truncate font-tm-mono text-[9px] text-tm-neg"
                  title={semantic.missing_required_semantics.join(" · ")}
                >
                  {zh ? "缺失" : "missing"}: {semantic.missing_required_semantics.join(", ")}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
        <div>
          <div className="font-tm-mono text-[9px] uppercase text-tm-muted">
            {zh ? "筛选证据" : "Screen evidence"}
          </div>
          <div className="font-tm-mono text-tm-fg">
            score {typeof screen?.score === "number" ? screen.score.toFixed(2) : "—"}
          </div>
          <div className="mt-1 font-tm-mono text-[9.5px] text-tm-muted">
            history {typeof screen?.history === "number" ? screen.history.toFixed(2) : "—"} · context n={screen?.context_n ?? 0}
          </div>
        </div>
        <div>
          <div className="font-tm-mono text-[9px] uppercase text-tm-muted">
            {zh ? "代理预测" : "Proxy prediction"}
          </div>
          {proxy?.active ? (
            <>
              <div className="font-tm-mono text-tm-fg">
                GOOD {pct(prediction.good)} · {zh ? "集中风险" : "concentration"} {pct(prediction.concentration)}
              </div>
              <div className="mt-1 font-tm-mono text-[9.5px] text-tm-muted">
                {zh ? "官方自相关估计" : "official self-corr estimate"} {pct(prediction.self_corr)} · {zh ? "分散化代理" : "diversification proxy"} {pct(prediction.marginal_proxy)}
              </div>
              <div
                className="mt-1 font-tm-mono text-[9px] text-tm-muted"
                title={zh
                  ? "分散化代理为 1 − 调整后自相关²，并非真实组合边际收益回归。"
                  : "Diversification proxy is 1 minus adjusted self-correlation squared, not a portfolio-level incremental-return regression."}
              >
                {zh ? "近 20% 时间留出集验证，仅以 15% 权重参与预筛" : "validated on the latest 20% holdout; 15% screen weight"}
              </div>
            </>
          ) : (
            <div className="text-tm-muted" title={proxy?.reason}>
              {zh ? "未通过样本或留出验证门槛" : "sample or holdout gate not met"}
            </div>
          )}
        </div>
      </div>
      {hypothesis?.falsification ? (
        <div className="mt-2 border-t border-tm-rule pt-2 font-tm-mono text-[9.5px] text-tm-muted">
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
      <div className="mb-1 font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
        {zh ? "历年 IS 概要" : "IS Summary by year"}
      </div>
      {rows && rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse font-mono text-[10.5px]">
            <thead>
              <tr className="border-b border-tm-rule text-tm-muted">
                {cols.map((c) => (
                  <th key={c} className="px-2 py-1 text-right font-tm-mono text-[9px] uppercase first:text-left">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-tm-rule/50">
                  {cols.map((c) => (
                    <td key={c} className="px-2 py-1 text-right tabular-nums text-tm-fg-2 first:text-left first:text-tm-fg">
                      {r[c] === null || r[c] === undefined
                        ? "—"
                        : typeof r[c] === "number"
                        ? (r[c] as number).toFixed(c === "year" ? 0 : 2)
                        : String(r[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : err ? (
        <p className="font-tm-mono text-[11px] text-tm-muted">
          {zh ? "无历年数据" : "no yearly data"}
        </p>
      ) : (
        <p className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-muted">
          <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} />
          {zh ? "拉取历年数据…" : "fetching yearly…"}
        </p>
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
      <code
        className={`block break-all font-tm-mono text-[11.5px] leading-snug ${alpha.is_blend ? "text-tm-accent" : "text-tm-fg"}`}
      >
        {alpha.expression}
      </code>

      {/* Blend provenance: this candidate was stitched from real parent alphas
          (family_focus == "blend" round). Old rows have no blend_parents and
          never render this — we don't retro-tag historical blends. */}
      {alpha.is_blend && alpha.blend_parents && alpha.blend_parents.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="rounded-sm border border-tm-accent/60 px-1.5 py-px font-tm-mono text-[9px] font-bold uppercase text-tm-accent">
              BLEND
            </span>
            <span className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
              {zh ? "父因子" : "parents"}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            {alpha.blend_parents.map((p, i) => (
              <code
                key={i}
                className="block break-all font-tm-mono text-[10.5px] leading-snug text-tm-muted"
              >
                {p}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {/* BRAIN's overall performance grade for this alpha + record timestamp */}
      <div className="flex items-center gap-2">
        <span className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
          {zh ? "性能评级" : "performance"}
        </span>
        <GradeBadge grade={alpha.grade} full />
        <span className="font-tm-mono text-[10px] text-tm-muted">
          {zh ? "BRAIN 综合评级" : "BRAIN overall grade"}
        </span>
        {alpha.created_at ? (
          <span
            className="ml-auto flex items-center gap-1 font-tm-mono text-[10px] tabular-nums text-tm-muted"
            title={zh ? "该回测结果记录时间(UTC+8)" : "backtest record time (UTC+8)"}
          >
            {fmtUtc8(alpha.created_at)}
            <span className="opacity-60">UTC+8</span>
          </span>
        ) : null}
      </div>

      {/* why rejected (failing checks) + retried tag */}
      <OutcomeTags alpha={alpha} />

      <div className="grid border border-tm-rule sm:grid-cols-[150px_1fr]">
        <div className="flex items-center border-b border-tm-rule px-3 py-2 sm:border-b-0 sm:border-r">
          <span className={`border px-1.5 py-px font-tm-mono text-[9px] font-bold uppercase ${verdict.cls}`}>
            {zh ? verdict.labelZh : verdict.labelEn}
          </span>
        </div>
        <div className="px-3 py-2 font-tm-mono text-[10.5px] leading-relaxed text-tm-fg-2">
          {zh ? verdict.detailZh : verdict.detailEn}
        </div>
      </div>

      {/* full IS metric set (6) + self-corr + BRAIN id */}
      <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-tm-fg-2 sm:grid-cols-4 lg:grid-cols-8">
        <Metric label="Sharpe" value={fmt(alpha.sharpe)} />
        <Metric label="Fitness" value={fmt(alpha.fitness)} />
        <Metric label={zh ? "换手" : "Turnover"} value={fmt(alpha.turnover)} />
        <Metric label={zh ? "收益" : "Returns"} value={fmt(alpha.returns)} />
        <Metric label="Drawdown" value={fmt(alpha.drawdown)} />
        <Metric label="Margin" value={fmt(alpha.margin, 4)} />
        <div className="flex flex-col">
          <span className="font-tm-mono text-[9px] uppercase tracking-[0.08em] text-tm-muted">
            {zh ? "自相关·官方" : "S-corr (BRAIN)"}
          </span>
          <span className="tabular-nums text-tm-fg">
            <OfficialSCorrCell alpha={alpha} zh={zh} />
          </span>
        </div>
        <div className="flex flex-col">
          <span className="font-tm-mono text-[9px] uppercase tracking-[0.08em] text-tm-muted">
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
          <span className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
            {zh ? "曲线" : "chart"}
          </span>
          <div className="flex gap-1">
            {CHART_KINDS.map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setChartKind(k)}
                className={`border px-1.5 py-px font-tm-mono text-[10px] ${chartKind === k ? "border-tm-accent text-tm-accent" : "border-tm-rule text-tm-muted hover:text-tm-fg"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {pnl && pnl.length > 0 ? (
          <BrainPnLChart points={pnl} kind={chartKind} />
        ) : pnlErr ? (
          <p className="font-tm-mono text-[11px] text-tm-muted">{pnlErr}</p>
        ) : (
          <p className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-muted">
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
      <span className="font-tm-mono text-[9px] uppercase tracking-[0.08em] text-tm-muted">
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
      <span
        className="cursor-help text-tm-muted"
        title={
          zh
            ? "该因子先未通过 BRAIN 的持仓集中度、子股票池 Sharpe 等提交前置检查，因此主流程未执行自相关请求。GOOD 及以上结果会在轮次末尾进入限量补查。"
            : "This factor failed an earlier BRAIN submission prerequisite, so the main path skipped the self-correlation request. GOOD-or-better rows enter a bounded post-run enrichment pass."
        }
      >
        {zh ? "未执行" : "skipped"}
      </span>
    );
  }
  if (status === "unavailable") {
    return (
      <span
        className="cursor-help text-tm-warn"
        title={
          zh
            ? "已请求 BRAIN 官方自相关，但在本轮限时轮询内尚未返回。后台回填任务会继续重试。"
            : "Official self-correlation was requested but did not settle within the bounded poll. The scheduled backfill will retry."
        }
      >
        {zh ? "暂不可用" : "unavail"}
      </span>
    );
  }
  return (
    <span
      className="cursor-help text-tm-muted"
      title={
        zh
          ? "BRAIN 官方自相关正在等待计算或尚未进入补查队列。0.70 是官方硬门槛，0.65–0.70 仅作预警。"
          : "Official BRAIN self-correlation is waiting to compute or has not entered enrichment yet. 0.70 is the hard limit; 0.65–0.70 is warning-only."
      }
    >
      {zh ? "待计算" : "pending"}
    </span>
  );
}

// Economic family of the alpha (from evolution.family_of, server-side). Labels
// mirror the FamilySelect dropdown so the same family reads the same everywhere.
// The six value-orthogonal sources get an accent-tinted border (the families we
// WANT); the saturated 'value'/'other' cluster stays muted.
const FAMILY_LABEL: Record<string, string> = {
  value: "value",
  dispersion: "dispersion",
  microstructure: "micro-pv",
  seasonality: "seasonal",
  overnight: "overnight",
  iv_term: "iv-term",
  iv_skew_dynamics: "skew-dynamics",
  iv_momentum: "iv-momentum",
  pcr_dynamics: "pcr-dynamics",
  option_breakeven: "breakeven",
  vrp: "vrp",
  quality: "quality",
  options: "iv-skew",
  lowvol: "low-vol",
  sentiment: "sentiment",
  momentum: "momentum",
  score: "factor-score",
  revision: "revision",
  other: "other",
};
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
  if (!family) return null;
  const label = FAMILY_LABEL[family] ?? family;
  const base = FAMILY_SATURATED.has(family)
    ? "border-tm-rule text-tm-muted"
    : "border-tm-accent/40 text-tm-fg-2";
  const cls = active ? "border-tm-accent text-tm-accent" : base;
  const shape = "shrink-0 border px-1 py-px font-tm-mono text-[9px] uppercase leading-none";
  if (!onClick) {
    return (
      <span title={family} className={`${shape} ${cls}`}>
        {label}
      </span>
    );
  }
  return (
    <span
      role="button"
      tabIndex={0}
      title={active ? `clear ${label} filter` : `filter: ${label}`}
      onClick={(e) => {
        e.stopPropagation();
        onClick(family);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.stopPropagation();
          e.preventDefault();
          onClick(family);
        }
      }}
      className={`${shape} cursor-pointer hover:border-tm-accent ${cls}`}
    >
      {label}
    </span>
  );
}

function GradeBadge({ grade, full = false }: { grade: string | null; full?: boolean }) {
  if (!grade) {
    return <span className="font-tm-mono text-[10px] text-tm-muted">—</span>;
  }
  const s = GRADE_STYLE[grade.toUpperCase()];
  const label = full ? grade : (s?.short ?? grade.slice(0, 4).toUpperCase());
  const cls = s?.cls ?? "border-tm-rule text-tm-muted";
  return (
    <span className={`border px-1 py-px font-tm-mono text-[9px] font-bold uppercase ${cls}`}>
      {label}
    </span>
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
        <span
          title={
            zh
              ? "对该因子做过一次参数自适应重试(调 decay / universe / truncation)"
              : "a settings-adaptation retry was run for this factor"
          }
          className="rounded-sm border border-tm-info/60 px-1.5 py-px font-tm-mono text-[9px] font-bold uppercase text-tm-info"
        >
          {zh ? "已调参重试" : "retried"}
        </span>
      ) : null}
      {checks.map((c) => (
        <span
          key={c}
          title={zh ? "未通过的在样内检查" : "failed in-sample check"}
          className="rounded-sm border border-tm-warn/60 px-1.5 py-px font-tm-mono text-[9px] font-bold uppercase text-tm-warn"
        >
          {checkLabel(c, zh)}
        </span>
      ))}
    </div>
  );
}

// BRAIN alpha id, shown inline on the row so the user can find the factor back on
// the WorldQuant platform without expanding. Click copies it (stopPropagation so it
// doesn't toggle the row). Only simulated candidates carry one.
function AlphaIdChip({ alphaId }: { alphaId: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span
      title={alphaId}
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(alphaId).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          },
          () => undefined,
        );
      }}
      className="shrink-0 cursor-pointer rounded-sm border border-tm-rule px-1 py-px font-tm-mono text-[9px] tabular-nums text-tm-muted hover:border-tm-accent/60 hover:text-tm-accent"
    >
      {copied ? "copied" : alphaId}
    </span>
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
          <span className="font-tm-mono text-[11px] text-tm-fg-2">
            {zh ? "挖矿进行中" : "mining in progress"} · {phase}
          </span>
          <span className="font-tm-mono text-[11px] tabular-nums text-tm-accent">
            {filled} / {job.n}
          </span>
          <button
            type="button"
            onClick={() => finish(job, "stopped")}
            title={
              zh
                ? "仅停止本页跟踪,不会取消已在运行的挖矿任务"
                : "stops tracking here; does not cancel the running job"
            }
            className="ml-auto font-tm-mono text-[10.5px] text-tm-muted hover:text-tm-fg"
          >
            {zh ? "停止跟踪" : "stop tracking"}
          </button>
        </div>
        <ProgressSegments filled={filled} total={job.n} />
        <span className="font-tm-mono text-[10px] text-tm-muted">
          {zh
            ? `生成池 ${job.generationTarget ?? job.n} 个表达式，最多执行 ${job.n} 次真实仿真 · 可离开本页，回来会继续跟踪`
            : `${job.generationTarget ?? job.n} generated expressions, at most ${job.n} real simulations · safe to leave`}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
      <span
        className="cursor-help font-tm-mono text-[11px] text-tm-fg-2"
        title={
          zh
            ? "真正提交到 WorldQuant BRAIN 的仿真上限，直接决定耗时和上游配额"
            : "Maximum real WorldQuant BRAIN simulations; this drives runtime and quota"
        }
      >
        {zh ? "仿真预算" : "simulation budget"}
      </span>
      <input
        value={n}
        onChange={(e) => setN(e.target.value)}
        inputMode="numeric"
        aria-label={zh ? "真实仿真预算" : "real simulation budget"}
        className="h-7 w-16 border border-tm-rule bg-tm-bg-2 px-2 text-center font-tm-mono text-[12px] text-tm-fg outline-none focus:border-tm-accent"
      />
      <span className="font-tm-mono text-[10px] text-tm-muted">←</span>
      <span
        className="cursor-help font-tm-mono text-[11px] text-tm-fg-2"
        title={
          zh
            ? "先在本地低成本生成更多表达式，再由 logic screen 排名并缩减到仿真预算"
            : "Cheap local pool ranked by the logic screen before consuming simulations"
        }
      >
        {zh ? "生成池" : "generation pool"}
      </span>
      <input
        value={generationTarget}
        onChange={(e) => setGenerationTarget(e.target.value)}
        inputMode="numeric"
        aria-label={zh ? "候选表达式生成池" : "generated expression pool"}
        className="h-7 w-16 border border-tm-rule bg-tm-bg-2 px-2 text-center font-tm-mono text-[12px] text-tm-fg outline-none focus:border-tm-accent"
      />
      <FamilySelect value={family} onChange={setFamily} zh={zh} />
      {selectedRun ? (
        <button
          type="button"
          onClick={reuseSelectedRun}
          className="h-7 border border-tm-rule px-2 font-tm-mono text-[10.5px] text-tm-muted hover:border-tm-accent/60 hover:text-tm-fg"
        >
          {zh ? `复用 RUN #${selectedRun.id}` : `reuse RUN #${selectedRun.id}`}
        </button>
      ) : null}
      <button
        type="button"
        onClick={go}
        disabled={state === "sending"}
        className="inline-flex items-center gap-1.5 rounded border border-tm-accent/60 bg-tm-accent px-3 py-1.5 font-tm-mono text-[11px] font-bold text-tm-bg transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {state === "sending" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
        ) : (
          <Play className="h-3.5 w-3.5" strokeWidth={1.75} />
        )}
        {zh ? "开始挖矿" : "Start mining"}
      </button>
      {state === "error" && errMsg ? (
        <span className="font-tm-mono text-[11px] text-tm-neg">{errMsg}</span>
      ) : doneMsg ? (
        <span className="inline-flex items-center gap-1.5 font-tm-mono text-[11px] text-tm-pos">
          <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
          {doneMsg}
        </span>
      ) : (
        <span className="font-tm-mono text-[10.5px] text-tm-muted">
          {zh
            ? parentRunId != null
              ? `将作为 RUN #${parentRunId} 的独立衍生轮次，原结果不会被覆盖`
              : "先筛选生成池，再在 GitHub Actions 上执行真实仿真"
            : parentRunId != null
              ? `new child of RUN #${parentRunId}; original results stay unchanged`
              : "rank the generated pool, then run real simulations on GitHub Actions"}
        </span>
      )}
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
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const labelOf = (o: BrainOutcome | "") =>
    o ? outcomeLabel(o, zh) : zh ? "全部状态" : "all";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-6 min-w-[92px] items-center justify-between gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none hover:border-tm-accent/60 focus:border-tm-accent"
      >
        <span className="text-tm-fg">{labelOf(value)}</span>
        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
      </button>
      {open ? (
        <ul
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 min-w-full border border-tm-rule bg-tm-bg-2 py-0.5 shadow-lg"
        >
          {OUTCOMES.map((o) => (
            <li key={o || "all"}>
              <button
                type="button"
                role="option"
                aria-selected={o === value}
                onClick={() => {
                  onChange(o);
                  setOpen(false);
                }}
                className={`block w-full whitespace-nowrap px-2 py-1 text-left font-tm-mono text-[11px] hover:bg-tm-bg-3 ${
                  o === value ? "text-tm-accent" : "text-tm-fg"
                }`}
              >
                {labelOf(o)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const labelOf = (v: string) =>
    v ? FAMILY_LABEL[v] ?? v : zh ? "全部家族" : "all families";
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={zh ? "按家族筛选结果" : "filter results by family"}
        className="flex h-6 min-w-[104px] items-center justify-between gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none hover:border-tm-accent/60 focus:border-tm-accent"
      >
        <span className="text-tm-fg">{labelOf(value)}</span>
        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
      </button>
      {open ? (
        <ul
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 min-w-full border border-tm-rule bg-tm-bg-2 py-0.5 shadow-lg"
        >
          {FAMILY_FILTER_KEYS.map((v) => (
            <li key={v || "all"}>
              <button
                type="button"
                role="option"
                aria-selected={v === value}
                onClick={() => {
                  onChange(v);
                  setOpen(false);
                }}
                className={`block w-full whitespace-nowrap px-2 py-1 text-left font-tm-mono text-[11px] hover:bg-tm-bg-3 ${
                  v === value ? "text-tm-accent" : "text-tm-fg"
                }`}
              >
                {labelOf(v)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

const FAMILIES: Array<[string, string, string]> = [
  ["", "普通(混合)", "normal"],
  ["options", "期权多机制", "options multi-mechanism"],
  ["lowvol", "low-vol", "low-vol"],
  ["sentiment", "sentiment", "sentiment"],
  ["momentum", "momentum", "momentum"],
  ["score", "factor-score", "factor-score"],
  ["revision", "revision", "revision"],
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
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const labelOf = (v: string) => {
    const f = FAMILIES.find((x) => x[0] === v) ?? FAMILIES[0];
    return zh ? f[1] : f[2];
  };
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={
          zh
            ? "挖矿家族。期权多机制会在 IV 偏度、偏度变化、期限结构、IV 动量、VRP、PCR 动态和 breakeven-forward 之间分配预算，不再只改同一模板的窗口。"
            : "Mining family. Options multi-mechanism allocates budget across IV skew, skew change, term structure, IV momentum, VRP, PCR dynamics, and breakeven-forward instead of window variants of one template."
        }
        className="flex h-7 min-w-[104px] items-center justify-between gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none hover:border-tm-accent/60 focus:border-tm-accent"
      >
        <span className="text-tm-fg">{labelOf(value)}</span>
        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
      </button>
      {open ? (
        <ul
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 min-w-full border border-tm-rule bg-tm-bg-2 py-0.5 shadow-lg"
        >
          {FAMILIES.map((f) => (
            <li key={f[0] || "normal"}>
              <button
                type="button"
                role="option"
                aria-selected={f[0] === value}
                onClick={() => {
                  onChange(f[0]);
                  setOpen(false);
                }}
                className={`block w-full whitespace-nowrap px-2 py-1 text-left font-tm-mono text-[11px] hover:bg-tm-bg-3 ${
                  f[0] === value ? "text-tm-accent" : "text-tm-fg"
                }`}
              >
                {zh ? f[1] : f[2]}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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
    (run.generated_n ?? 0) === 0 &&
    (run.persisted_n ?? 0) === 0
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
  const raw = `${run.status ?? ""} ${run.screen_status ?? ""}`.toLowerCase();
  if (raw.includes("fail") || raw.includes("error")) return "text-tm-neg";
  if (raw.includes("run") || raw.includes("queue") || raw.includes("screen")) return "text-tm-accent";
  if (raw.includes("complete") || raw.includes("pass")) return "text-tm-pos";
  return "text-tm-muted";
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

  if (run.status === "failed" || isEmptyCompletedRun(run)) {
    return zh ? "先按错误信息恢复配置，再复用本轮参数重跑。" : "Recover the reported failure, then reuse this run.";
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
    return zh
      ? `证据筛选主动保留了 ${requested - screened} 个仿真名额，低可信候选没有被回填消耗预算。先检查字段覆盖率与候选证据，再决定是否扩大生成池。`
      : `The evidence screen intentionally left ${requested - screened} simulation slots unused instead of backfilling weak candidates. Review field coverage and candidate evidence before widening generation.`;
  }
  if (generated <= requested) {
    return zh ? "生成池没有形成候选冗余，下一轮可扩大到仿真预算的约 2 倍。" : "The pool had no ranking headroom; try roughly 2× the simulation budget.";
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
  return zh ? "等待本轮完成后再判断瓶颈。" : "Wait for completion before diagnosing the bottleneck.";
}

function RunSelector({
  runs,
  selectedRunId,
  onChange,
  zh,
}: {
  runs: BrainMiningRun[];
  selectedRunId: number | null;
  onChange: (id: number | null) => void;
  zh: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = runs.find((run) => run.id === selectedRunId) ?? null;

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const buttonLabel = selected
    ? `RUN #${selected.id}`
    : selectedRunId != null
      ? `RUN #${selectedRunId}`
      : zh
        ? "全部结果"
        : "all results";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-7 min-w-[150px] items-center justify-between gap-2 border border-tm-rule bg-tm-bg-2 px-2 font-tm-mono text-[11px] text-tm-fg outline-none hover:border-tm-accent/60 focus:border-tm-accent"
      >
        <span className="truncate text-left">
          {buttonLabel}
          {selected ? ` · ${runSourceLabel(selected, zh)}` : ""}
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
      </button>
      {open ? (
        <ul
          role="listbox"
          className="absolute left-0 top-full z-50 mt-1 max-h-72 min-w-[250px] overflow-y-auto border border-tm-rule bg-tm-bg-2 py-0.5 shadow-lg"
        >
          <li>
            <button
              type="button"
              role="option"
              aria-selected={selectedRunId === null}
              onClick={() => {
                onChange(null);
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between gap-3 border-b border-tm-rule px-2 py-1.5 text-left font-tm-mono text-[10.5px] hover:bg-tm-bg-3 ${selectedRunId === null ? "text-tm-accent" : "text-tm-fg"}`}
            >
              <span>{zh ? "历史兼容视图 · 全部结果" : "legacy view · all results"}</span>
              <span className="text-[9px] text-tm-muted">ALL</span>
            </button>
          </li>
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                role="option"
                aria-selected={run.id === selectedRunId}
                onClick={() => {
                  onChange(run.id);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-3 px-2 py-1.5 text-left font-tm-mono text-[10.5px] hover:bg-tm-bg-3 ${run.id === selectedRunId ? "text-tm-accent" : "text-tm-fg"}`}
              >
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">RUN #{run.id} · {runSourceLabel(run, zh)}</span>
                  <span className="text-[9px] text-tm-muted">
                    {run.family_focus || (zh ? "混合家族" : "mixed family")} · {fmtUtc8(run.created_at ?? run.started_at)}
                  </span>
                </span>
                <span className={runStatusClass(run)}>{runStatusLabel(run, zh)}</span>
              </button>
            </li>
          ))}
          {runs.length === 0 ? (
            <li className="px-2 py-1.5 font-tm-mono text-[10.5px] text-tm-muted">
              {zh ? "暂无运行记录" : "no run records"}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

function RunLedger({
  run,
  selectedRunId,
  runsError,
  runsTotal,
  zh,
}: {
  run: BrainMiningRun | null;
  selectedRunId: number | null;
  runsError: string | null;
  runsTotal: number;
  zh: boolean;
}) {
  if (!run) {
    return (
      <div className="border-b border-tm-rule px-3 py-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-[10.5px] text-tm-muted">
          <span className="uppercase tracking-wider text-tm-accent">{zh ? "运行账本" : "run ledger"}</span>
          {selectedRunId != null ? (
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
          <p className="mt-1 font-tm-mono text-[10px] text-tm-warn">
            {zh ? `运行账本读取失败：${runsError}` : `run ledger unavailable: ${runsError}`}
          </p>
        ) : null}
      </div>
    );
  }

  const funnel: Array<[string, string]> = [
    [zh ? "仿真预算" : "sim budget", runCount(run, "requested_n")],
    [
      zh ? "生成" : "generated",
      `${runCount(run, "generated_n")} / ${run.generation_target_n ?? "—"}`,
    ],
    [zh ? "入选仿真" : "selected", runCount(run, "screened_n")],
    [zh ? "已仿真" : "simulated", runCount(run, "simulated_n")],
    [zh ? "已入库" : "persisted", runCount(run, "persisted_n")],
  ];
  const outcome = [
    [zh ? "通过" : "passed", runCount(run, "passed_n"), "text-tm-pos"],
    [zh ? "存疑" : "flagged", runCount(run, "flagged_n"), "text-tm-warn"],
    [zh ? "淘汰" : "rejected", runCount(run, "rejected_n"), "text-tm-muted"],
    [zh ? "仿真错误" : "sim errors", runCount(run, "sim_error_n"), "text-tm-neg"],
  ] as const;

  return (
    <div className="border-b border-tm-rule px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-[10.5px]">
        <span className="uppercase tracking-wider text-tm-accent">RUN #{run.id}</span>
        <span className="text-tm-fg-2">{runSourceLabel(run, zh)}</span>
        <span className="text-tm-muted">{run.family_focus || (zh ? "混合家族" : "mixed family")}</span>
        {run.parent_run_id != null ? (
          <span className="text-tm-info">{zh ? `源 RUN #${run.parent_run_id}` : `from RUN #${run.parent_run_id}`}</span>
        ) : null}
        <span className={runStatusClass(run)}>{runStatusLabel(run, zh)}</span>
        <span className="text-tm-muted">{fmtUtc8(run.created_at ?? run.started_at)} UTC+8</span>
        {runsTotal > 0 ? <span className="ml-auto text-tm-muted">{runsTotal} {zh ? "轮" : "runs"}</span> : null}
      </div>
      <div className="mt-2 grid grid-cols-5 gap-2 border-t border-tm-rule/60 pt-1.5">
        {funnel.map(([label, value]) => (
          <div key={label} className="flex min-w-0 flex-col font-tm-mono">
            <span className="truncate text-[9px] uppercase tracking-wider text-tm-muted">{label}</span>
            <span className="tabular-nums text-[12px] text-tm-fg">{value}</span>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-tm-mono text-[10px]">
        {outcome.map(([label, count, className]) => (
          <span key={label} className={className}>{label} {count}</span>
        ))}
        {run.screen_status ? <span className="text-tm-muted">{zh ? "筛选" : "screen"}: {run.screen_status}</span> : null}
      </div>
      {run.screen_detail || run.error_detail ? (
        <p className="mt-1 break-words font-tm-mono text-[10px] leading-relaxed text-tm-warn">
          {run.error_detail || run.screen_detail}
        </p>
      ) : null}
      <div className="mt-2 grid gap-px border border-tm-rule bg-tm-rule md:grid-cols-[0.7fr_0.7fr_0.7fr_2fr]">
        {[
          [zh ? "筛选利用" : "screen use", runRate(run.screened_n, run.generated_n)],
          [zh ? "通过率" : "pass yield", runRate(run.passed_n, run.simulated_n)],
          [zh ? "仿真错误" : "sim errors", runRate(run.sim_error_n, run.simulated_n)],
        ].map(([label, value]) => (
          <div key={label} className="bg-tm-bg px-2 py-1.5 font-tm-mono">
            <div className="text-[9px] uppercase tracking-wider text-tm-muted">{label}</div>
            <div className="mt-0.5 text-[11px] tabular-nums text-tm-fg">{value}</div>
          </div>
        ))}
        <div className="bg-tm-bg px-2 py-1.5 font-tm-mono">
          <div className="text-[9px] uppercase tracking-wider text-tm-accent">
            {zh ? "下一步" : "next action"}
          </div>
          <div className="mt-0.5 text-[10px] leading-relaxed text-tm-fg-2">
            {runNextStep(run, zh)}
          </div>
        </div>
      </div>
    </div>
  );
}


export function BrainMiningPanel() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [outcome, setOutcome] = useState<BrainOutcome | "">("");
  const [q, setQ] = useState("");
  const [sharpeMin, setSharpeMin] = useState("");
  const [familyFilter, setFamilyFilter] = useState("");
  const [sort, setSort] = useState<string>("created_at");
  const [descending, setDescending] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const [data, setData] = useState<{ alphas: BrainAlpha[]; total: number } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [runs, setRuns] = useState<BrainMiningRun[] | null>(null);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runsLoading, setRunsLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(
    () => loadActiveJob()?.runId ?? null,
  );
  // A run chosen by the user or by a just-dispatched manual job must not be
  // replaced by a later refresh's default selection.
  const selectionTouched = useRef(selectedRunId != null);

  const loadRuns = useCallback(async (preferRunId?: number | null) => {
    setRunsLoading(true);
    try {
      const res = await fetchBrainRuns(RECENT_RUN_LIMIT);
      const recent = sortRecentRuns(Array.isArray(res.runs) ? res.runs : []).slice(0, RECENT_RUN_LIMIT);
      setRuns(recent);
      setRunsTotal(typeof res.total === "number" ? res.total : recent.length);
      setRunsError(null);
      if (preferRunId != null) {
        selectionTouched.current = true;
        setSelectedRunId(preferRunId);
      } else if (!selectionTouched.current) {
        const preferred = recent.find(isManualRun) ?? recent[0] ?? null;
        setSelectedRunId(preferred?.id ?? null);
      }
    } catch (e) {
      // The ledger is a rollout-era enhancement. Keep the legacy all-results
      // query usable when this endpoint is missing or temporarily unavailable.
      setRunsError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunsLoading(false);
    }
  }, []);

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
    try {
      const res = await fetchBrainAlphas(query);
      if (sequence !== loadSequence.current) return;
      setData(res);
      setLoadError(null);
    } catch (e) {
      if (sequence !== loadSequence.current) return;
      setLoadError(e instanceof Error ? e.message : String(e));
      setData({ alphas: [], total: 0 });
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  // Do not leave the previous run's rows painted while a newly selected run is
  // loading. This keeps the run label and candidate evidence in lockstep.
  useEffect(() => {
    setData(null);
    setLoadError(null);
  }, [selectedRunId]);

  const handleRunSelection = useCallback((runId: number | null) => {
    selectionTouched.current = true;
    setSelectedRunId(runId);
    setData(null);
    setLoadError(null);
    setPage(0);
    setExpanded(new Set());
  }, []);

  const handleMiningStarted = useCallback(
    (runId: number | null) => {
      if (runId == null) return;
      selectionTouched.current = true;
      setSelectedRunId(runId);
      setData(null);
      setLoadError(null);
      setPage(0);
      setExpanded(new Set());
      void loadRuns(runId);
    },
    [loadRuns],
  );

  const handleMiningComplete = useCallback(
    (runId: number | null) => {
      if (runId != null) {
        selectionTouched.current = true;
        setSelectedRunId(runId);
        setData(null);
        setLoadError(null);
        setPage(0);
        setExpanded(new Set());
        void loadRuns(runId);
      } else {
        // Legacy POST responses do not identify a run. Refresh the current
        // compatibility query without changing the user's selected run.
        void load();
        void loadRuns();
      }
    },
    [load, loadRuns],
  );

  // reset to page 0 whenever a filter or the page size changes
  useEffect(() => {
    setPage(0);
    setExpanded(new Set());
  }, [selectedRunId, outcome, q, sharpeMin, familyFilter, sort, descending, pageSize]);

  function toggle(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSort(col: string) {
    if (sort === col) setDescending((d) => !d);
    else {
      setSort(col);
      setDescending(true);
    }
  }

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const meta = `${total} ${zh ? "个 alpha" : "alphas"}`;
  const selectedRun = runs?.find((run) => run.id === selectedRunId) ?? null;
  const recentRuns = runs ?? [];
  const selectedRunFailed = Boolean(
    selectedRun &&
      ((selectedRun.status ?? "").toLowerCase() === "failed" ||
        (selectedRun.status ?? "").toLowerCase() === "error" ||
        isEmptyCompletedRun(selectedRun)),
  );
  const selectedRunFailureDetail =
    selectedRun?.error_detail || selectedRun?.screen_detail || null;

  const INPUT =
    "h-6 bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11px] text-tm-fg outline-none focus:border-tm-accent placeholder:text-tm-muted";

  return (
    <TmScreen>
      <TmPane title={zh ? "挖矿控制" : "MINING.CONTROL"}>
        <MineButton
          selectedRun={selectedRun}
          onStarted={handleMiningStarted}
          onComplete={handleMiningComplete}
        />
      </TmPane>

      <TmPane
        title="WORLDQUANT.BRAIN"
        meta={
          <button
            type="button"
            onClick={() => void load()}
            className="flex items-center gap-1.5 text-tm-muted hover:text-tm-fg"
            title={zh ? "刷新" : "refresh"}
          >
            {meta}
            <RefreshCw className="h-3 w-3" strokeWidth={1.75} />
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
          <span className="font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
            {zh ? "查看运行" : "view run"}
          </span>
          <RunSelector
            runs={recentRuns}
            selectedRunId={selectedRunId}
            onChange={handleRunSelection}
            zh={zh}
          />
          {runsLoading ? (
            <span className="font-tm-mono text-[10px] text-tm-muted">{zh ? "读取账本…" : "loading ledger…"}</span>
          ) : runsError ? (
            <span className="font-tm-mono text-[10px] text-tm-warn">{zh ? "兼容模式" : "legacy mode"}</span>
          ) : null}
        </div>
        <RunLedger
          run={selectedRun}
          selectedRunId={selectedRunId}
          runsError={runsError}
          runsTotal={runsTotal}
          zh={zh}
        />
        {/* filter bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
          <OutcomeSelect value={outcome} onChange={setOutcome} zh={zh} />
          <FamilyFilterSelect value={familyFilter} onChange={setFamilyFilter} zh={zh} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={zh ? "搜索表达式或编码…" : "search expr or code…"}
            className={`${INPUT} w-56`}
          />
          <input
            value={sharpeMin}
            onChange={(e) => setSharpeMin(e.target.value)}
            placeholder={zh ? "Sharpe ≥" : "Sharpe ≥"}
            inputMode="decimal"
            className={`${INPUT} w-24`}
          />
          <span className="ml-auto font-tm-mono text-[10px] text-tm-muted">
            {zh ? "排序:" : "sort:"}
          </span>
          {SORTS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggleSort(s)}
              className={`inline-flex items-center gap-0.5 font-tm-mono text-[10px] uppercase ${sort === s ? "text-tm-accent" : "text-tm-muted hover:text-tm-fg"}`}
            >
              {s === "created_at" ? (zh ? "时间" : "date") : s}
              {sort === s ? (
                descending ? (
                  <ArrowDown className="h-2.5 w-2.5" strokeWidth={2} />
                ) : (
                  <ArrowUp className="h-2.5 w-2.5" strokeWidth={2} />
                )
              ) : null}
            </button>
          ))}
        </div>

        {/* column header */}
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto_auto_auto_auto_auto] items-center gap-2.5 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[9px] uppercase tracking-wider text-tm-muted">
          <span>{zh ? "表达式" : "expr"}</span>
          <span className="w-12 text-right">Sharpe</span>
          <span className="w-12 text-right">Fitness</span>
          <span className="w-12 text-right">{zh ? "换手" : "TO"}</span>
          <span className="w-12 text-right">{zh ? "收益" : "Ret"}</span>
          <span className="w-12 text-right">{zh ? "回撤" : "DD"}</span>
          <span className="w-14 text-right">Margin</span>
          <span
            className="w-12 cursor-help text-right"
            title={
              zh
                ? "BRAIN 官方自相关性:与已提交(ACTIVE)因子的最大相关性。0.70 为官方硬门槛,0.65–0.70 仅预警。"
                : "BRAIN official maximum correlation vs ACTIVE alphas. 0.70 is the hard limit; 0.65–0.70 is warning-only."
            }
          >
            S-corr
          </span>
          <span
            className="w-14 cursor-help text-right text-tm-info"
            title={
              zh
                ? "调整后自相关性:额外计入已挖出但暂未提交的通过因子。仍以 0.70 为硬门槛,0.65–0.70 只提示组合拥挤风险。"
                : "Adjusted correlation also counts passed-but-unsubmitted factors. The hard limit remains 0.70; 0.65–0.70 only warns about crowding."
            }
          >
            S-corr⁺
          </span>
          <span className="w-24 text-right">{zh ? "编码" : "code"}</span>
          <span className="w-14 text-right">{zh ? "评级" : "grade"}</span>
          <span className="w-20 text-right">{zh ? "结论" : "verdict"}</span>
        </div>

        {/* rows */}
        {data === null ? (
          <p className="flex items-center gap-2 px-3 py-5 font-tm-mono text-[11px] text-tm-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {zh ? "加载中…" : "loading…"}
          </p>
        ) : data.alphas.length === 0 ? (
          <p className="px-3 py-5 font-tm-mono text-[11px] leading-relaxed text-tm-muted">
            {loadError
              ? (zh ? `读取失败: ${loadError}` : `load failed: ${loadError}`)
              : selectedRunFailed
              ? zh
                ? `本轮在候选生成或仿真阶段失败，没有产生可展示结果。${selectedRunFailureDetail ? ` 原因: ${selectedRunFailureDetail}` : ""}`
                : `This run failed during candidate generation or simulation and produced no displayable results.${selectedRunFailureDetail ? ` Reason: ${selectedRunFailureDetail}` : ""}`
              : total === 0
              ? zh
                ? "还没有挖矿结果。点上方「开始挖矿」跑一轮,或等每日 08:00 UTC 自动运行。前提:已在「设置」连接 BRAIN 账号。"
                : "No mining results yet. Click 'Start mining' above, or wait for the daily 08:00 UTC run. Requires a connected BRAIN account in Settings."
              : zh
              ? "没有符合筛选的结果。"
              : "No results match the filters."}
          </p>
        ) : (
          <ul className="flex flex-col">
            {data.alphas.flatMap((a, i) => {
              const open = expanded.has(a.id);
              const verdict = candidateVerdict(a);
              const prev = i > 0 ? data.alphas[i - 1] : null;
              // Batch divider: only under the default time sort are rows from the
              // same mining round contiguous. Any metric sort interleaves batches,
              // so a divider would be noise — suppress it there. Rows carry the
              // per-row separator manually now (divide-y is gone) so a batch
              // boundary can swap the thin rule for the accent divider below.
              const newBatch =
                sort === "created_at" &&
                prev != null &&
                (a.batch_started_at ?? "") !== (prev.batch_started_at ?? "");
              const row = (
                <li
                  key={a.id}
                  className={i > 0 && !newBatch ? "border-t border-tm-rule" : ""}
                >
                  <button
                    type="button"
                    onClick={() => toggle(a.id)}
                    className="grid w-full grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto_auto_auto_auto_auto] items-center gap-2.5 px-3 py-2 text-left hover:bg-tm-bg-2"
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      {open ? (
                        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
                      ) : (
                        <ChevronRight className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
                      )}
                      <FamilyBadge
                        family={a.family}
                        active={familyFilter === a.family}
                        onClick={(fam) =>
                          setFamilyFilter((cur) => (cur === fam ? "" : fam))
                        }
                      />
                      <code
                        className={`truncate font-tm-mono text-[11px] ${a.is_blend ? "text-tm-accent" : "text-tm-fg"}`}
                      >
                        {a.expression}
                      </code>
                      {a.submitted_at ? (
                        <CheckCircle2 className="h-3 w-3 shrink-0 text-tm-pos" strokeWidth={1.75} />
                      ) : null}
                    </span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.sharpe)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.fitness)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.turnover)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.returns)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.drawdown)}</span>
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.margin, 4)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2"><OfficialSCorrCell alpha={a} zh={zh} /></span>
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums"><SCorrValue value={a.self_correlation_adj} /></span>
                    <span className="flex w-24 justify-end">
                      {a.alpha_id ? (
                        <AlphaIdChip alphaId={a.alpha_id} />
                      ) : (
                        <span className="font-tm-mono text-[10px] text-tm-muted">—</span>
                      )}
                    </span>
                    <span className="flex w-14 justify-end">
                      <GradeBadge grade={a.grade} />
                    </span>
                    <span className="flex w-20 justify-end">
                      <span
                        title={zh ? verdict.detailZh : verdict.detailEn}
                        className={`whitespace-nowrap border px-1 py-px font-tm-mono text-[9px] font-bold uppercase ${verdict.cls}`}
                      >
                        {zh ? verdict.labelZh : verdict.labelEn}
                      </span>
                    </span>
                  </button>
                  {open ? <RowDetail alpha={a} onDone={() => void load()} /> : null}
                </li>
              );
              if (!newBatch) return [row];
              // The accent line "where two boxes meet"; hover reveals the round's
              // dispatch time (UTC+8). Labels the batch BELOW it (time sort is DESC,
              // so crossing down enters the round dispatched at this timestamp).
              return [
                <li key={`div-${a.id}`} aria-hidden>
                  <div
                    className="group relative flex cursor-help items-center py-1.5"
                    title={
                      a.batch_started_at
                        ? `${zh ? "本批次发起于 " : "batch dispatched "}${fmtUtc8(a.batch_started_at)} UTC+8`
                        : undefined
                    }
                  >
                    <span className="h-0.5 flex-1 bg-tm-accent/30 transition-colors group-hover:bg-tm-accent/60" />
                    <span className="whitespace-nowrap px-2 font-tm-mono text-[9px] uppercase tracking-wide text-tm-muted opacity-0 transition-opacity group-hover:opacity-100">
                      {a.batch_started_at ? `${fmtUtc8(a.batch_started_at)} UTC+8` : "—"}
                    </span>
                    <span className="h-0.5 flex-1 bg-tm-accent/30 transition-colors group-hover:bg-tm-accent/60" />
                  </div>
                </li>,
                row,
              ];
            })}
          </ul>
        )}

        {/* pagination + custom page size */}
        {total > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-tm-rule px-3 py-2 font-tm-mono text-[11px] text-tm-muted">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="hover:text-tm-fg disabled:opacity-40"
            >
              ‹ {zh ? "上一页" : "prev"}
            </button>
            <span className="flex items-center gap-2 tabular-nums">
              <span>
                {zh
                  ? `第 ${page + 1} / ${pageCount} 页 · 共 ${total} 条`
                  : `page ${page + 1} / ${pageCount} · ${total} total`}
              </span>
              <span className="flex items-center gap-1">
                <span>{zh ? "每页" : "per page"}</span>
                <input
                  value={String(pageSize)}
                  onChange={(e) => {
                    const n = parseInt(e.target.value.replace(/\D/g, ""), 10);
                    // clamp 1..200 (server also caps limit at 200); empty -> keep
                    if (Number.isFinite(n) && n > 0) setPageSize(Math.min(200, n));
                    else if (e.target.value === "") setPageSize(1);
                  }}
                  inputMode="numeric"
                  aria-label={zh ? "每页条数" : "rows per page"}
                  className="h-5 w-12 border border-tm-rule bg-tm-bg-2 px-1 text-center text-tm-fg outline-none focus:border-tm-accent"
                />
                <span>{zh ? "条" : "rows"}</span>
              </span>
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={page >= pageCount - 1}
              className="hover:text-tm-fg disabled:opacity-40"
            >
              {zh ? "下一页" : "next"} ›
            </button>
          </div>
        ) : null}
      </TmPane>
    </TmScreen>
  );
}
