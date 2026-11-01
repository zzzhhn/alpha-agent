"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmTable } from "@/components/tm/TmTable";
import TurnoverStudy from "./TurnoverStudy";
import RecommendationNavChart, { type RecommendationNavPoint } from "@/components/charts/RecommendationNavChart";

type Evidence = {
  status: string; sleeve: string; policy_id?: string; as_of?: string;
  valuation_current?: boolean; overdue_orders?: number;
  cost_bps_per_side?: number; top_n?: number;
  observations?: number; observed_max_drawdown?: number; mean_rebalance_turnover?: number | null;
  series?: RecommendationNavPoint[];
  missing_sessions?: number; stale_sessions?: number;
  windows?: Record<string, { status: string; net_return: number | null; spy_return: number | null; rsp_return: number | null }>;
  exceptions?: { reason: string; count: number }[];
  account?: { cumulative_return: number | null; pending_orders: number; transaction_costs: number };
  comparison?: { from: string; to: string; strategy: number; spy: number | null; rsp: number | null; cash_no_interest: number } | null;
};
const pct = (n: number | null | undefined) => n == null ? "—" : `${(100 * n).toFixed(2)}%`;

export default function InvestmentEvidence({ sleeve, policyId, showStudy = true }: { sleeve: "tactical" | "strategic"; policyId?: string | null; showStudy?: boolean }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [result, setResult] = useState<Evidence | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null); setError(false);
    apiGet<Evidence>(`/api/l2/evidence?sleeve=${sleeve}`).then(r => { if (active) setResult(r); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [sleeve, retry]);
  const data = result?.sleeve === sleeve ? result : null;
  const mismatch = !!data?.policy_id && !!policyId && data.policy_id !== policyId;
  const comparison = !mismatch ? data?.comparison : null;
  return <TmPane title={zh ? "跟随这套策略，结果怎样？" : "What happens when this policy is followed?"}
    meta={zh ? "做多验证账户，收益优势尚未证实" : "Long-only validation book; edge unproven"} bodyClassName="gap-3 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-tm-muted">
      <span>{sleeve === "strategic" ? (zh ? "战略 60 日" : "Strategic 60d") : (zh ? "战术 5 日" : "Tactical 5d")} · {data?.policy_id ?? policyId ?? "—"}</span>
      <TmLinkButton href="/paper">{zh ? "打开模拟仓" : "Open paper account"}</TmLinkButton>
    </div>
    {error ? <div role="alert" className="flex items-center gap-3 text-xs text-tm-warn">{zh ? "绩效证据暂不可用，不能据此判断收益。" : "Performance evidence unavailable; returns cannot be assessed."}<TmButton variant="secondary" onClick={() => setRetry(n => n + 1)}>{zh ? "重试" : "Retry"}</TmButton></div>
      : !data ? <p role="status" className="text-xs text-tm-muted">{zh ? "正在读取对应策略账本…" : "Loading this policy's book…"}</p>
      : data.status === "identity_quarantined" ? <p role="status" className="text-xs text-tm-warn">{zh ? "旧账本已隔离：PARA 代码被另一家公司重新使用，历史成交混入了错误证券。已停止继续模拟成交，并隐藏无效收益；原始记录保留供核查，不会直接改成 PSKY 或补造价格。" : "Book quarantined: PARA was reused by an unrelated issuer, contaminating historical fills. Further simulated execution is stopped and invalid returns are hidden. Original records remain intact; no automatic PSKY substitution or invented prices."}</p>
      : mismatch ? <p className="text-xs text-tm-warn">{zh ? "推荐与验证账户的策略版本不同，已隐藏不匹配的收益。" : "Recommendation and book policy versions differ. Unmatched returns hidden."}</p>
      : <>
        <p className="text-xs text-tm-warn">{data.overdue_orders ? (zh ? `执行延迟：${data.overdue_orders} 笔订单待核验，不宜作为正常运行的投资记录。` : `Execution delayed: ${data.overdue_orders} orders require review.`)
          : data.status === "history_gaps" ? (zh ? "账本存在未成交或缺测记录，不能作为完整跟随收益。" : "The book contains unfilled orders or missing marks; it is not a complete following record.")
          : zh ? "这是研究验证，不是买入承诺；没有足够证据时可以不操作。" : "Research validation, not a buy instruction. No action is a valid outcome."}</p>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[[zh ? "同区间策略净收益" : "Matched-period net return", pct(comparison?.strategy)], ["SPY", pct(comparison?.spy)], ["RSP", pct(comparison?.rsp)], [zh ? "现金，不计利息" : "Cash, no interest", comparison ? "0.00%" : "—"]].map(([label,value]) => <div key={label}><div className="text-xs text-tm-muted">{label}</div><div className="mt-1 font-tm-mono text-lg text-tm-fg">{value}</div></div>)}
        </div>
        <p className="text-xs text-tm-muted">{comparison ? `${comparison.from} → ${comparison.to}` : (zh ? "等待至少两次账本估值，暂不比较。" : "Awaiting two book valuations before comparison.")} · {zh ? "账本估值截至" : "Book valued through"} {data.as_of ?? "—"}{!data.valuation_current ? (zh ? "，不是今日市值。" : "; not today's market value.") : ""}</p>
        <RecommendationNavChart series={data.series ?? []} zh={zh} />
        <div className="overflow-x-auto">
          <TmTable className="text-left">
            <caption className="py-2 text-left text-tm-muted">{zh ? "近期实际持仓收益，不是预测准确率" : "Recent held-portfolio returns, not prediction accuracy"}</caption>
            <thead className="text-tm-muted"><tr>{[zh ? "窗口" : "Window", zh ? "策略扣费后" : "Net strategy", "SPY", "RSP"].map(label => <th key={label} className="border-b border-tm-rule py-2 pr-4 font-normal">{label}</th>)}</tr></thead>
            <tbody>{[5, 21].map(n => { const w = data.windows?.[String(n)]; return <tr key={n}>
              <th className="py-2 pr-4 font-normal">{n} {zh ? "交易日" : "sessions"}</th>
              {w?.status === "ready" ? [w.net_return, w.spy_return, w.rsp_return].map((v, i) => <td key={i} className="py-2 pr-4">{pct(v)}</td>) : <td colSpan={3} className="py-2 text-tm-muted">{zh ? "完整日估值不足，继续积累；缺价不会记成零收益。" : "Not enough complete daily marks; missing quotes are not zero returns."}</td>}
            </tr>; })}</tbody>
          </TmTable>
        </div>
        <div className="grid gap-3 border-t border-tm-rule pt-3 text-xs md:grid-cols-3">
          <p>{zh ? "估值记录，非独立样本" : "Valuations, not independent trials"}：{data.observations ?? 0}</p>
          <p>{zh ? "已观测最大回撤" : "Observed maximum drawdown"}：{data.observations ? pct(data.observed_max_drawdown) : "—"}</p>
          <p>{zh ? "平均调仓换手（双边）" : "Mean rebalance turnover (two-way)"}：{pct(data.mean_rebalance_turnover)}</p>
        </div>
        <p className="text-xs text-tm-muted">{zh ? `累计交易成本 $${data.account?.transaction_costs?.toFixed(2) ?? "—"}。策略包含首次建仓和后续交易成本；SPY / RSP 同日起买入持有，扣除相同单边假设的建仓成本。` : `Cumulative costs $${data.account?.transaction_costs?.toFixed(2) ?? "—"}. Strategy includes entry and later trading costs. SPY / RSP buy-and-hold starts on the same date, charging the same assumed entry cost.`}</p>
        {!!(data.missing_sessions || data.stale_sessions) && <p className="text-xs text-tm-warn">{zh ? `历史缺测 ${data.missing_sessions ?? 0} 日，缺价估值 ${data.stale_sessions ?? 0} 日。补记已有持仓市值不等于补做当时未执行的调仓；历史断档期间的回撤可能被低估。` : `${data.missing_sessions ?? 0} missing sessions; ${data.stale_sessions ?? 0} stale marks. Revaluing existing shares does not recreate missed trades; drawdown during historical gaps may be understated.`}</p>}
        <p className="text-xs text-tm-warn">{zh ? "当前支持的结论：继续观察，不因榜单变化自动交易。降低频率不保证提高收益，需要独立对照。" : "Supported action: observe; do not automatically trade ranking changes. Lower frequency does not guarantee better returns; compare independently."}</p>
        <p className="text-xs text-tm-muted">{zh ? `当前规则：Top ${data.top_n ?? "—"}，按周检查调仓，每个交易日收盘估值。每边假设综合成本 ${data.cost_bps_per_side ?? "—"} bps，不是券商报价。使用行情源复权收盘价，未逐笔处理公司行动、税费和现金利息，不是实盘成交净值。` : `Top ${data.top_n ?? "—"}, weekly rebalance checks, daily close marks. Assumed all-in cost ${data.cost_bps_per_side ?? "—"} bps per side, not a broker quote. Uses provider-adjusted closes, without a full corporate-action ledger, taxes or cash interest. Not live brokerage performance.`}</p>
        {showStudy ? <TurnoverStudy key={sleeve} sleeve={sleeve} /> : null}
      </>}
  </TmPane>;
}
