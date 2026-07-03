"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2, AlertTriangle, Send, RefreshCw } from "lucide-react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmScreen, TmPane } from "@/components/tm/TmPane";
import {
  fetchBrainAlphas,
  submitBrainAlpha,
  type BrainAlpha,
  type BrainOutcome,
} from "@/lib/api/brain";

/**
 * Phase E5: the review surface for real WorldQuant BRAIN mining results.
 * Candidates are bucketed by how they fared on the platform; the operator's one
 * decision is whether to submit a survivor to their BRAIN account. Design intent
 * (per the UI/UX principles): lead with the survivors that need a decision
 * (PASSED, then FLAGGED), demote the noise (REJECTED / SIM_ERROR) into a
 * collapsed tail, and make Submit — the only outward, quota-spending action —
 * the visually dominant control with a confirm step for damping.
 */
function fmt(v: number | null | undefined, d = 2): string {
  return typeof v === "number" && !Number.isNaN(v) ? v.toFixed(d) : "—";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-tm-mono text-[9px] uppercase tracking-[0.08em] text-tm-muted">
        {label}
      </span>
      <span className="font-mono text-[12px] tabular-nums text-tm-fg">{value}</span>
    </div>
  );
}

type SubmitState = "idle" | "confirm" | "sending" | "done" | "error";

function SubmitControl({
  alpha,
  onDone,
}: {
  alpha: BrainAlpha;
  onDone: () => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const router = useRouter();
  const [state, setState] = useState<SubmitState>(
    alpha.submitted_at ? "done" : "idle",
  );
  const [msg, setMsg] = useState<string | null>(alpha.brain_status);

  if (state === "done") {
    return (
      <span className="inline-flex items-center gap-1.5 font-tm-mono text-[11px] text-tm-pos">
        <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.75} />
        {(zh ? "已提交" : "submitted")}
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
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

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
            {zh ? "确认提交到 BRAIN" : "Confirm submit"}
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

function AlphaCard({
  alpha,
  submittable,
  onDone,
}: {
  alpha: BrainAlpha;
  submittable: boolean;
  onDone: () => void;
}) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const decay = (alpha.settings?.decay as number | undefined) ?? 0;
  return (
    <li className="flex flex-col gap-2 px-3 py-2.5">
      <code className="block break-all font-tm-mono text-[12px] leading-snug text-tm-fg">
        {alpha.expression}
      </code>
      <div className="grid grid-cols-3 gap-x-4 gap-y-1.5 sm:grid-cols-6">
        <Metric label="Sharpe" value={fmt(alpha.sharpe)} />
        <Metric label="Fitness" value={fmt(alpha.fitness)} />
        <Metric label={zh ? "换手" : "Turnover"} value={fmt(alpha.turnover)} />
        <Metric label="Drawdown" value={fmt(alpha.drawdown)} />
        <Metric label="Self-corr" value={fmt(alpha.self_correlation)} />
        <Metric label="Decay" value={String(decay)} />
      </div>
      {alpha.self_correlation_with ? (
        <div className="inline-flex w-fit items-center gap-1.5 rounded border border-tm-warn/50 px-2 py-0.5 font-tm-mono text-[10.5px] text-tm-warn">
          <AlertTriangle className="h-3 w-3" strokeWidth={1.75} />
          {(zh ? "与已有 alpha 相关: " : "correlates with: ") +
            alpha.self_correlation_with}
        </div>
      ) : null}
      {submittable ? (
        <div className="flex items-center justify-between">
          <span className="font-tm-mono text-[10px] text-tm-muted">
            {alpha.alpha_id ? `BRAIN ${alpha.alpha_id}` : ""}
          </span>
          <SubmitControl alpha={alpha} onDone={onDone} />
        </div>
      ) : null}
    </li>
  );
}

const OUTCOME_META: Record<
  BrainOutcome,
  { title: (zh: boolean) => string; cls: string }
> = {
  passed: {
    title: (zh) => (zh ? "通过 · 可提交" : "PASSED · ready to submit"),
    cls: "text-tm-pos",
  },
  flagged: {
    title: (zh) => (zh ? "存疑 · 需审查后提交" : "FLAGGED · review before submit"),
    cls: "text-tm-warn",
  },
  rejected: {
    title: (zh) => (zh ? "未过闸" : "REJECTED · below gates"),
    cls: "text-tm-muted",
  },
  sim_error: {
    title: (zh) => (zh ? "仿真失败" : "SIM ERROR"),
    cls: "text-tm-neg",
  },
};

export function BrainMiningPanel() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [showTail, setShowTail] = useState(false);
  // Auth-gated endpoint: fetch client-side (in the browser, where the Next.js
  // middleware injects the auth token), NOT from a server component — SSR skips
  // middleware, so /api/brain/alphas would 401 and render "no results" even
  // when the user has mined alphas. (client.ts: "Auth-gated endpoints are only
  // called client-side.")
  const [alphas, setAlphas] = useState<BrainAlpha[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetchBrainAlphas(100);
      setAlphas(res.alphas);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
      setAlphas([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    const g: Record<BrainOutcome, BrainAlpha[]> = {
      passed: [], flagged: [], rejected: [], sim_error: [],
    };
    for (const a of alphas ?? []) g[a.outcome]?.push(a);
    return g;
  }, [alphas]);

  // Loading (first fetch not yet resolved).
  if (alphas === null) {
    return (
      <TmScreen>
        <TmPane title="WORLDQUANT.BRAIN" meta={zh ? "加载中" : "loading"}>
          <p className="flex items-center gap-2 px-3 py-5 font-tm-mono text-[11.5px] text-tm-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {zh ? "读取挖矿结果…" : "loading mining results…"}
          </p>
        </TmPane>
      </TmScreen>
    );
  }

  const meta = `${groups.passed.length} ${zh ? "通过" : "PASS"} · ${groups.flagged.length} ${zh ? "存疑" : "FLAG"} · ${groups.rejected.length + groups.sim_error.length} ${zh ? "淘汰" : "OUT"}`;

  if (alphas.length === 0) {
    return (
      <TmScreen>
        <TmPane title="WORLDQUANT.BRAIN" meta={zh ? "无结果" : "no results"}>
          <p className="px-3 py-5 font-tm-mono text-[11.5px] leading-relaxed text-tm-muted">
            {loadError
              ? (zh ? `读取失败: ${loadError}` : `load failed: ${loadError}`)
              : zh
              ? "还没有挖矿结果。到 GitHub → Actions → brain-mining-loop 手动跑一轮(或等每日 08:00 UTC 自动运行)。GA 会生成 FASTEXPR、在你的 BRAIN 账号上真实仿真、按 Sharpe/Fitness/换手/自相关过闸,过闸的 alpha 会出现在这里供你审查提交。前提:已在「设置」连接 BRAIN 账号。"
              : "No mining results yet. Run GitHub → Actions → brain-mining-loop (or wait for the daily 08:00 UTC run). The GA generates FASTEXPR, simulates on your BRAIN account, and gates on Sharpe/Fitness/Turnover/self-correlation; survivors appear here for you to review and submit. Requires a connected BRAIN account in Settings."}
          </p>
        </TmPane>
      </TmScreen>
    );
  }

  const renderGroup = (outcome: BrainOutcome, submittable: boolean) => {
    const items = groups[outcome];
    if (items.length === 0) return null;
    const m = OUTCOME_META[outcome];
    return (
      <TmPane key={outcome} title="" meta="">
        <div className={`border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[11px] font-bold uppercase tracking-wider ${m.cls}`}>
          {m.title(zh)} · {items.length}
        </div>
        <ul className="flex flex-col divide-y divide-tm-rule">
          {items.map((a) => (
            <AlphaCard
              key={a.id}
              alpha={a}
              submittable={submittable}
              onDone={() => void load()}
            />
          ))}
        </ul>
      </TmPane>
    );
  };

  return (
    <TmScreen>
      <TmPane
        title="WORLDQUANT.BRAIN"
        meta={
          <span className="flex items-center gap-2">
            {meta}
            <button
              type="button"
              onClick={() => void load()}
              className="text-tm-muted hover:text-tm-fg"
              aria-label={zh ? "刷新" : "refresh"}
              title={zh ? "刷新" : "refresh"}
            >
              <RefreshCw className="h-3 w-3" strokeWidth={1.75} />
            </button>
          </span>
        }
      >
        <p className="px-3 py-2.5 font-tm-mono text-[11px] leading-relaxed text-tm-fg-2">
          {zh
            ? "GA 挖出、在你 BRAIN 账号上真实仿真过的 alpha。通过下方闸门的可直接提交(提交是唯一对外动作,需你逐条确认)。"
            : "Alphas the GA mined and simulated on your real BRAIN account. Gate survivors can be submitted (submit is the only outward action — you confirm each one)."}
        </p>
      </TmPane>

      {renderGroup("passed", true)}
      {renderGroup("flagged", true)}

      {groups.rejected.length + groups.sim_error.length > 0 ? (
        <TmPane
          title={zh ? "淘汰候选" : "DISCARDED"}
          meta={`${groups.rejected.length + groups.sim_error.length}`}
        >
          <button
            type="button"
            onClick={() => setShowTail((s) => !s)}
            className="w-full px-3 py-2 text-left font-tm-mono text-[11px] text-tm-muted hover:text-tm-fg"
          >
            {showTail
              ? zh ? "收起" : "hide"
              : zh ? "展开未过闸 / 仿真失败的候选" : "show rejected / sim-error candidates"}
          </button>
          {showTail ? (
            <div className="flex flex-col">
              {renderGroup("rejected", false)}
              {renderGroup("sim_error", false)}
            </div>
          ) : null}
        </TmPane>
      ) : null}
    </TmScreen>
  );
}
