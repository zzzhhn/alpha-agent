"use client";

import { useState } from "react";
import { apiGet } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmButton } from "@/components/tm/TmButton";
import { TmTable, TmTableFrame, TmTableHead, TmTableBody, TmTableRow, TmTableHeaderCell, TmTableCell } from "@/components/tm/TmTable";

type Result = { mode: string; status: string; net_return?: number; max_drawdown?: number; two_way_turnover?: number; trade_batches?: number; date?: string; tickers?: string[] };
type Study = { status: string; from?: string; to?: string; causal_targets?: number; excluded_batches?: number; cost_bps_per_side?: number; results?: Result[] };
const pct = (n?: number) => n == null ? "—" : `${(100 * n).toFixed(2)}%`;

export default function TurnoverStudy({ sleeve }: { sleeve: "tactical" | "strategic" }) {
  const { locale } = useLocale(); const zh = locale === "zh";
  const [study, setStudy] = useState<Study | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(false);
  const run = async () => {
    setBusy(true); setError(false);
    try { setStudy(await apiGet<Study>(`/api/l2/turnover-study?sleeve=${sleeve}`)); }
    catch { setError(true); } finally { setBusy(false); }
  };
  const names: Record<string, string> = zh
    ? {recorded: "原始已记录目标", monthly: "每月首个可用目标", band: "1 个百分点免调仓带", spy: "持有 SPY", rsp: "持有 RSP", cash: "现金，不计利息"}
    : {recorded: "Recorded targets", monthly: "First available target / month", band: "1pp no-trade band", spy: "Hold SPY", rsp: "Hold RSP", cash: "Cash, no interest"};
  return <div className="space-y-3 border-t border-tm-rule pt-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-tm-muted">{zh ? "低换手与简单基准对照：按需读取最多 120 天的既有数据，不改线上策略，不调用 LLM。" : "Turnover and simple baselines: replay up to 120 days of stored data on demand. No live policy changes or LLM calls."}</p>
      <TmButton variant="secondary" loading={busy} onClick={() => void run()}>{zh ? "查看只读对照实验" : "Run read-only comparison"}</TmButton>
    </div>
    {error ? <p role="alert" className="text-xs text-tm-neg">{zh ? "实验暂不可用，可重试；线上策略未改动。" : "Study unavailable. Retry; live policy is unchanged."}</p> : null}
    {study?.status === "retrospective_only" ? <>
      <p className="text-xs text-tm-warn">{zh ? `历史反事实，不是新策略的前瞻收益：${study.from} 至 ${study.to}，${study.causal_targets} 组目标，每边 ${study.cost_bps_per_side} bps；排除 ${study.excluded_batches} 组非因果或不匹配目标。` : `Retrospective, not forward performance: ${study.from} to ${study.to}; ${study.causal_targets} targets; ${study.cost_bps_per_side} bps/side; ${study.excluded_batches} invalid batches excluded.`}</p>
      <TmTableFrame><TmTable caption={zh ? "固定方案，未择优调参" : "Fixed variants, no parameter selection"}>
        <TmTableHead><TmTableRow>{(zh ? ["方案", "净收益", "最大回撤", "累计双边换手", "交易批次"] : ["Variant", "Net return", "Max drawdown", "Total two-way turnover", "Trade batches"]).map(label => <TmTableHeaderCell key={label}>{label}</TmTableHeaderCell>)}</TmTableRow></TmTableHead>
        <TmTableBody>{study.results?.map(r => <TmTableRow key={r.mode}>
          <TmTableCell>{names[r.mode] ?? r.mode}</TmTableCell>
          {r.status === "ready" ? <><TmTableCell>{pct(r.net_return)}</TmTableCell><TmTableCell>{pct(r.max_drawdown)}</TmTableCell><TmTableCell>{pct(r.two_way_turnover)}</TmTableCell><TmTableCell>{r.trade_batches}</TmTableCell></>
            : <TmTableCell colSpan={4}>{zh ? "缺少价格或目标无效，未计算" : "Missing prices or invalid targets; not computed"} · {r.date} {r.tickers?.join(", ")}</TmTableCell>}
        </TmTableRow>)}</TmTableBody>
      </TmTable></TmTableFrame>
      <p className="text-xs text-tm-muted">{zh ? "按日估值、允许碎股、计入首次建仓成本；不含分红、税费和现金利息。月度方案只能使用当月首个既有目标，不是完整月初重选。缺价格不填零。不能凭最高一列就升级策略。" : "Daily marks, fractional shares, initial entry costs included; no dividends, taxes or cash interest. Monthly uses the first stored target, not a fresh month-start selection. Missing prices are not zero-filled. Do not promote a policy merely because it ranks first here."}</p>
    </> : study ? <p className="text-xs text-tm-warn">{zh ? "可用的同政策、成交前目标不足，或超过读取上限，暂不能作比较。" : "Too few same-policy pre-close targets, or the history limit was reached."}</p> : null}
  </div>;
}
