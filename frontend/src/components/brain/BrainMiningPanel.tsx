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
  fetchAlphaPnl,
  fetchAlphaYearly,
  fetchMineStatus,
  submitBrainAlpha,
  triggerMining,
  type BrainAlpha,
  type BrainAlphaQuery,
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
type ActiveJob = { startedAt: string; n: number; dispatchedAt: number };
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
    return raw ? (JSON.parse(raw) as ActiveJob) : null;
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
      <code className="block break-all font-tm-mono text-[11.5px] leading-snug text-tm-fg">
        {alpha.expression}
      </code>

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
        <Metric
          label={zh ? "自相关·调整" : "S-corr⁺ (adj)"}
          value={fmt(alpha.self_correlation_adj)}
        />
      </div>

      <SettingsRow settings={alpha.settings} />

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

// Official BRAIN self-correlation. BRAIN computes it only AFTER submit (pre-submit
// the IS SELF_CORRELATION check is PENDING and /correlations/self is empty), so an
// unsubmitted alpha shows a "pending" marker — not a bare dash that reads as a bug.
// Use the adjusted S-corr⁺ for pre-submit diversity gating.
function OfficialSCorrCell({ alpha, zh }: { alpha: BrainAlpha; zh: boolean }) {
  if (typeof alpha.self_correlation === "number") {
    return <>{fmt(alpha.self_correlation)}</>;
  }
  if (!alpha.submitted_at) {
    return (
      <span
        className="cursor-help text-tm-muted"
        title={
          zh
            ? "官方自相关由 BRAIN 惰性计算,通常提交前即可获得;本行显示待定表示挖矿/回填时尚未算完或未拉取。右侧「调整后 S-corr⁺」在官方值基础上还计入本地未提交的通过因子,是其超集,据此把关更严格。"
            : "The official self-corr is computed lazily by BRAIN and is usually available pre-submit; 待定 here means it wasn't ready/fetched at mine or backfill time. The adjusted S-corr⁺ on the right is a superset (official plus your local not-yet-submitted passers), so gating on it is stricter."
        }
      >
        {zh ? "待定" : "pend"}
      </span>
    );
  }
  return <>—</>;
}

// Economic family of the alpha (from evolution.family_of, server-side). Labels
// mirror the FamilySelect dropdown so the same family reads the same everywhere.
// The six value-orthogonal sources get an accent-tinted border (the families we
// WANT); the saturated 'value'/'other' cluster stays muted.
const FAMILY_LABEL: Record<string, string> = {
  value: "value",
  options: "options",
  lowvol: "low-vol",
  sentiment: "sentiment",
  momentum: "momentum",
  score: "factor-score",
  revision: "revision",
  other: "other",
};
const FAMILY_SATURATED = new Set(["value", "other"]);
function FamilyBadge({ family }: { family?: string | null }) {
  if (!family) return null;
  const label = FAMILY_LABEL[family] ?? family;
  const cls = FAMILY_SATURATED.has(family)
    ? "border-tm-rule text-tm-muted"
    : "border-tm-accent/40 text-tm-fg-2";
  return (
    <span
      title={family}
      className={`shrink-0 border px-1 py-px font-tm-mono text-[9px] uppercase leading-none ${cls}`}
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
function MineButton({ onComplete }: { onComplete: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [n, setN] = useState("12");
  const [family, setFamily] = useState("options");
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

  const finish = useCallback(() => {
    setJob(null);
    setStatus(null);
    setDoneMsg(
      zh ? "本轮挖矿完成,结果已刷新" : "mining round complete, results refreshed",
    );
    onComplete();
  }, [onComplete, zh]);

  // Poll the round's progress while a job is active.
  useEffect(() => {
    if (!job) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick(current: ActiveJob) {
      try {
        const s = await fetchMineStatus(current.startedAt);
        if (!alive) return;
        setStatus({ running: s.running });
        setMined(s.mined);
        const elapsed = Date.now() - current.dispatchedAt;
        const done =
          // GH says nothing is queued/running (past the startup grace) → done.
          (s.running === false && elapsed > GRACE_MS) ||
          // GH unavailable → fall back to the raw count reaching the target.
          (s.running === null && s.mined >= current.n) ||
          // Safety: never lock the control forever on a stuck/failed run.
          elapsed > MAX_TRACK_MS;
        if (done) {
          finish();
          return;
        }
      } catch {
        if (alive && Date.now() - current.dispatchedAt > MAX_TRACK_MS) {
          finish();
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
      const r = await triggerMining(nc, family);
      setMined(0);
      setStatus(null);
      setJob({ startedAt: r.started_at, n: r.n_candidates, dispatchedAt: Date.now() });
      setState("idle");
    } catch (e) {
      setState("error");
      setErrMsg(e instanceof Error ? e.message : String(e));
    }
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
            onClick={finish}
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
            ? "在 GitHub Actions 上真实仿真,每完成一个候选亮一格 · 可离开本页,回来会继续跟踪"
            : "real sims on GitHub Actions; one cell per candidate · safe to leave, tracking resumes"}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
      <span className="font-tm-mono text-[11px] text-tm-fg-2">
        {zh ? "候选数" : "candidates"}
      </span>
      <input
        value={n}
        onChange={(e) => setN(e.target.value)}
        inputMode="numeric"
        className="h-7 w-16 border border-tm-rule bg-tm-bg-2 px-2 text-center font-tm-mono text-[12px] text-tm-fg outline-none focus:border-tm-accent"
      />
      <FamilySelect value={family} onChange={setFamily} zh={zh} />
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
            ? "在 GitHub Actions 上真实仿真,不占用页面"
            : "runs on GitHub Actions, no page hold"}
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

const FAMILIES: Array<[string, string, string]> = [
  ["", "普通(混合)", "normal"],
  ["options", "options", "options"],
  ["lowvol", "low-vol", "low-vol"],
  ["sentiment", "sentiment", "sentiment"],
  ["momentum", "momentum", "momentum"],
  ["score", "factor-score", "factor-score"],
  ["revision", "revision", "revision"],
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
            ? "挖矿家族。普通=混合（value 已饱和）；options=期权偏度（最高夏普正交源）；low-vol、momentum、sentiment、factor-score=新正交源（待验证）；revision=分析师修正（偏弱）"
            : "mining family. normal=mixed (value saturated); options=IV-skew; low-vol/momentum/sentiment/factor-score=new orthogonal sources (unvalidated); revision=analyst revisions (weak)"
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


export function BrainMiningPanel() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [outcome, setOutcome] = useState<BrainOutcome | "">("");
  const [q, setQ] = useState("");
  const [sharpeMin, setSharpeMin] = useState("");
  const [sort, setSort] = useState<string>("created_at");
  const [descending, setDescending] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const [data, setData] = useState<{ alphas: BrainAlpha[]; total: number } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const query = useMemo<BrainAlphaQuery>(
    () => ({
      limit: pageSize,
      offset: page * pageSize,
      outcome: outcome || undefined,
      q: q.trim() || undefined,
      sharpe_min: sharpeMin ? Number(sharpeMin) : undefined,
      sort,
      descending,
    }),
    [page, pageSize, outcome, q, sharpeMin, sort, descending],
  );

  const load = useCallback(async () => {
    try {
      const res = await fetchBrainAlphas(query);
      setData(res);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
      setData({ alphas: [], total: 0 });
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  // reset to page 0 whenever a filter or the page size changes
  useEffect(() => {
    setPage(0);
  }, [outcome, q, sharpeMin, sort, descending, pageSize]);

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

  const INPUT =
    "h-6 bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11px] text-tm-fg outline-none focus:border-tm-accent placeholder:text-tm-muted";

  return (
    <TmScreen>
      <TmPane title={zh ? "挖矿控制" : "MINING.CONTROL"}>
        <MineButton onComplete={load} />
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
        {/* filter bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-tm-rule px-3 py-2">
          <OutcomeSelect value={outcome} onChange={setOutcome} zh={zh} />
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
                ? "BRAIN 官方自相关性:与你已提交(ACTIVE)因子的最大相关性"
                : "BRAIN official: max self-correlation vs your ACTIVE (submitted) alphas"
            }
          >
            S-corr
          </span>
          <span
            className="w-14 cursor-help text-right text-tm-info"
            title={
              zh
                ? "调整后自相关性:额外计入已挖出但暂未提交的通过因子后,重新计算的最大相关性"
                : "Adjusted: recomputed to also count your passed-but-unsubmitted mined factors"
            }
          >
            S-corr⁺
          </span>
          <span className="w-24 text-right">{zh ? "编码" : "code"}</span>
          <span className="w-14 text-right">{zh ? "评级" : "grade"}</span>
          <span className="w-12 text-right">{zh ? "状态" : "status"}</span>
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
                      <FamilyBadge family={a.family} />
                      <code className="truncate font-tm-mono text-[11px] text-tm-fg">
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
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums text-tm-info">{fmt(a.self_correlation_adj)}</span>
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
                    <span className="flex w-12 justify-end">
                      <span className={`border px-1 py-px font-tm-mono text-[9px] font-bold uppercase ${OUTCOME_CLS[a.outcome]}`}>
                        {outcomeLabel(a.outcome, zh)}
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
