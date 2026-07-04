"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { BrainPnLChart } from "@/components/brain/BrainPnLChart";
import {
  fetchBrainAlphas,
  fetchAlphaPnl,
  submitBrainAlpha,
  type BrainAlpha,
  type BrainAlphaQuery,
  type BrainOutcome,
  type PnlPoint,
} from "@/lib/api/brain";

const PAGE_SIZE = 20;

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
function RowDetail({ alpha, onDone }: { alpha: BrainAlpha; onDone: () => void }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [pnl, setPnl] = useState<PnlPoint[] | null>(null);
  const [pnlErr, setPnlErr] = useState<string | null>(null);

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

  return (
    <div className="flex flex-col gap-3 border-t border-tm-rule bg-tm-bg-2 px-3 py-3">
      <code className="block break-all font-tm-mono text-[11.5px] leading-snug text-tm-fg">
        {alpha.expression}
      </code>
      <div className="grid grid-cols-3 gap-2 font-mono text-[11px] text-tm-fg-2 sm:grid-cols-6">
        <Metric label="Sharpe" value={fmt(alpha.sharpe)} />
        <Metric label="Fitness" value={fmt(alpha.fitness)} />
        <Metric label={zh ? "换手" : "Turnover"} value={fmt(alpha.turnover)} />
        <Metric label="Drawdown" value={fmt(alpha.drawdown)} />
        <Metric label="Self-corr" value={fmt(alpha.self_correlation)} />
        <Metric label="BRAIN" value={alpha.alpha_id ?? "—"} />
      </div>

      <div>
        <div className="mb-1 font-tm-mono text-[10px] uppercase tracking-wider text-tm-muted">
          {zh ? "累计 PnL 曲线" : "cumulative PnL"}
        </div>
        {pnl && pnl.length > 0 ? (
          <BrainPnLChart points={pnl} />
        ) : pnlErr ? (
          <p className="font-tm-mono text-[11px] text-tm-muted">{pnlErr}</p>
        ) : (
          <p className="flex items-center gap-2 font-tm-mono text-[11px] text-tm-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.75} />
            {zh ? "从 BRAIN 拉取 PnL…" : "fetching PnL from BRAIN…"}
          </p>
        )}
      </div>

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

// ── main panel ───────────────────────────────────────────────────────────────
const OUTCOMES: Array<BrainOutcome | ""> = ["", "passed", "flagged", "rejected", "sim_error"];
const SORTS = ["created_at", "sharpe", "fitness", "turnover"] as const;

export function BrainMiningPanel() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [page, setPage] = useState(0);
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
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      outcome: outcome || undefined,
      q: q.trim() || undefined,
      sharpe_min: sharpeMin ? Number(sharpeMin) : undefined,
      sort,
      descending,
    }),
    [page, outcome, q, sharpeMin, sort, descending],
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

  // reset to page 0 whenever a filter changes
  useEffect(() => {
    setPage(0);
  }, [outcome, q, sharpeMin, sort, descending]);

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
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const meta = `${total} ${zh ? "个 alpha" : "alphas"}`;

  const INPUT =
    "h-6 bg-tm-bg-2 border border-tm-rule px-2 font-tm-mono text-[11px] text-tm-fg outline-none focus:border-tm-accent placeholder:text-tm-muted";

  return (
    <TmScreen>
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
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as BrainOutcome | "")}
            className={INPUT}
          >
            {OUTCOMES.map((o) => (
              <option key={o || "all"} value={o}>
                {o ? outcomeLabel(o, zh) : zh ? "全部状态" : "all"}
              </option>
            ))}
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={zh ? "搜索表达式…" : "search expression…"}
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
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto] items-center gap-3 border-b border-tm-rule px-3 py-1.5 font-tm-mono text-[9px] uppercase tracking-wider text-tm-muted">
          <span>{zh ? "表达式" : "expression"}</span>
          <span className="w-14 text-right">Sharpe</span>
          <span className="w-14 text-right">Fitness</span>
          <span className="w-14 text-right">{zh ? "换手" : "TO"}</span>
          <span className="w-12 text-right">S-corr</span>
          <span className="w-14 text-right">{zh ? "状态" : "status"}</span>
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
          <ul className="flex flex-col divide-y divide-tm-rule">
            {data.alphas.map((a) => {
              const open = expanded.has(a.id);
              return (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => toggle(a.id)}
                    className="grid w-full grid-cols-[1fr_auto_auto_auto_auto_auto] items-center gap-3 px-3 py-2 text-left hover:bg-tm-bg-2"
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      {open ? (
                        <ChevronDown className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
                      ) : (
                        <ChevronRight className="h-3 w-3 shrink-0 text-tm-muted" strokeWidth={1.75} />
                      )}
                      <code className="truncate font-tm-mono text-[11px] text-tm-fg">
                        {a.expression}
                      </code>
                      {a.submitted_at ? (
                        <CheckCircle2 className="h-3 w-3 shrink-0 text-tm-pos" strokeWidth={1.75} />
                      ) : null}
                    </span>
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.sharpe)}</span>
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.fitness)}</span>
                    <span className="w-14 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.turnover)}</span>
                    <span className="w-12 text-right font-mono text-[11px] tabular-nums text-tm-fg-2">{fmt(a.self_correlation)}</span>
                    <span className="flex w-14 justify-end">
                      <span className={`border px-1 py-px font-tm-mono text-[9px] font-bold uppercase ${OUTCOME_CLS[a.outcome]}`}>
                        {outcomeLabel(a.outcome, zh)}
                      </span>
                    </span>
                  </button>
                  {open ? <RowDetail alpha={a} onDone={() => void load()} /> : null}
                </li>
              );
            })}
          </ul>
        )}

        {/* pagination */}
        {total > PAGE_SIZE ? (
          <div className="flex items-center justify-between border-t border-tm-rule px-3 py-2 font-tm-mono text-[11px] text-tm-muted">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="hover:text-tm-fg disabled:opacity-40"
            >
              ‹ {zh ? "上一页" : "prev"}
            </button>
            <span>
              {zh ? "第" : "page"} {page + 1} / {pageCount}
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
