"use client";

import { useState } from "react";
import { apiGet, apiPost, ApiException } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmInput, TmSelect, TmTextarea } from "@/components/tm/TmField";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";

type Profile = { horizon_months: number; drawdown_review_pct: number; review_frequency: "weekly" | "monthly"; max_position_pct: number; max_sector_pct: number; holdings_as_of: string; holdings: { ticker: string; weight_pct: number }[] };
type Review = { status: string; warnings?: { code: string; subject: string; actual_pct: number; limit_pct: number }[]; unknown_sector_tickers?: string[]; unallocated_pct?: number; holdings_age_days?: number };

export default function InvestmentProfile() {
  const { locale } = useLocale(); const zh = locale === "zh";
  const [open, setOpen] = useState(false); const [loading, setLoading] = useState(false);
  const [error, setError] = useState(""); const [signin, setSignin] = useState(false);
  const [months, setMonths] = useState(""); const [drawdown, setDrawdown] = useState("");
  const [position, setPosition] = useState(""); const [sector, setSector] = useState("");
  const [frequency, setFrequency] = useState("weekly"); const [holdings, setHoldings] = useState("");
  const [asOf, setAsOf] = useState(""); const [review, setReview] = useState<Review | null>(null);
  const [dirty, setDirty] = useState(false);
  const fail = (e: unknown) => {
    setSignin(e instanceof ApiException && e.status === 401);
    setError(zh ? "无法读取或保存，请确认登录状态、字段范围和持仓合计不超过 100%。" : "Unable to load or save. Check sign-in, field ranges and total allocation ≤100%.");
  };
  const load = async () => {
    setOpen(true); setLoading(true); setError(""); setSignin(false);
    try {
      const { profile: p } = await apiGet<{ profile: Profile | null }>("/api/user/investment/profile");
      if (p) { setMonths(String(p.horizon_months)); setDrawdown(String(p.drawdown_review_pct)); setPosition(String(p.max_position_pct)); setSector(String(p.max_sector_pct)); setFrequency(p.review_frequency); setAsOf(p.holdings_as_of); setHoldings(p.holdings.map(h => `${h.ticker}, ${h.weight_pct}`).join("\n")); setReview(await apiGet<Review>("/api/user/investment/review")); }
      else { setMonths(""); setDrawdown(""); setPosition(""); setSector(""); setFrequency("weekly"); setAsOf(""); setHoldings(""); setReview(null); }
      setDirty(false);
    } catch(e) { fail(e); } finally { setLoading(false); }
  };
  const save = async () => {
    setError(""); setLoading(true); setReview(null);
    try {
      const parsed = holdings.trim() ? holdings.trim().split("\n").map(line => {
        const cells = line.split(",").map(s => s.trim());
        if (cells.length !== 2 || !cells[0] || !cells[1] || !Number.isFinite(Number(cells[1]))) throw new Error("invalid holding");
        return { ticker: cells[0].toUpperCase(), weight_pct: Number(cells[1]) };
      }) : [];
      await apiPost("/api/user/investment/profile", { horizon_months: Number(months), drawdown_review_pct: Number(drawdown), max_position_pct: Number(position), max_sector_pct: Number(sector), review_frequency: frequency, holdings_as_of: asOf, holdings: parsed });
      setDirty(false); setReview(await apiGet<Review>("/api/user/investment/review"));
    } catch(e) { fail(e); } finally { setLoading(false); }
  };
  const update = (setter: (v: string) => void) => (v: string) => { setter(v); setDirty(true); setReview(null); };
  return <TmPane title={zh ? "我的投资计划" : "My investment plan"} bodyClassName="gap-3 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-tm-muted">{zh ? "先明确期限与现有持仓，再讨论候选。未填写时不生成个性化仓位。" : "Start with your horizon and holdings. No personalized allocation without a profile."}</p>
      <TmButton variant="secondary" loading={loading} aria-expanded={open} onClick={() => open ? setOpen(false) : void load()}>{open ? (zh ? "收起" : "Collapse") : (zh ? "查看与编辑" : "View / edit")}</TmButton>
    </div>
    {open ? <>
      <div className="grid gap-4 md:grid-cols-3">
        <TmInput type="number" label={zh ? "计划持有（月）" : "Horizon (months)"} min={1} max={120} value={months} onChange={update(setMonths)} />
        <TmInput type="number" label={zh ? "触发复查的组合回撤（%）" : "Drawdown review trigger (%)"} min={1} max={80} value={drawdown} onChange={update(setDrawdown)} />
        <TmSelect label={zh ? "计划复查频率" : "Review cadence"} value={frequency} onChange={update(setFrequency)} options={[{value: "weekly", label: zh ? "每周" : "Weekly"}, {value: "monthly", label: zh ? "每月" : "Monthly"}]} />
        <TmInput type="number" label={zh ? "自设单股上限（%）" : "Your position cap (%)"} min={1} max={100} value={position} onChange={update(setPosition)} />
        <TmInput type="number" label={zh ? "自设行业上限（%）" : "Your sector cap (%)"} min={1} max={100} value={sector} onChange={update(setSector)} />
        <TmInput type="date" label={zh ? "持仓数据日期" : "Holdings date"} value={asOf} onChange={update(setAsOf)} />
      </div>
      <TmTextarea label={zh ? "实际持仓权重，手动录入" : "Actual holdings, manually entered"} hint={zh ? "每行：股票代码, 占总资产百分比。例如 AAPL, 5。留空表示没有填写股票持仓；剩余比例仅视为未分配。" : "One per line: ticker, percent of total assets. Example: AAPL, 5. The remainder is unallocated, not assumed cash."} value={holdings} onChange={update(setHoldings)} rows={4} />
      <p className="text-xs text-tm-warn">{zh ? "回撤阈值仅保存为规划输入，当前不监测实际账户回撤，不保证止损成交；不会连接券商或自动交易。模拟仓也不等于你的真实持仓。" : "Drawdown is a planning input, not monitored account drawdown or guaranteed stop execution. No broker connection or automatic trading. Paper holdings are not actual holdings."}</p>
      {error ? <p role="alert" className="text-xs text-tm-neg">{error}</p> : null}
      {signin ? <TmLinkButton href="/signin">{zh ? "登录" : "Sign in"}</TmLinkButton> : <TmButton variant="primary" loading={loading} disabled={!months || !drawdown || !position || !sector || !asOf} onClick={() => void save()}>{zh ? "保存并检查组合" : "Save and review portfolio"}</TmButton>}
      {dirty ? <p className="text-xs text-tm-muted">{zh ? "存在未保存修改，旧检查结果已隐藏。" : "Unsaved changes. Previous review hidden."}</p> : null}
      {review?.status === "ready" ? <div className="space-y-2 border-t border-tm-rule pt-3 text-xs">
        <p>{zh ? `持仓填报距今 ${review.holdings_age_days} 天；未分配 ${review.unallocated_pct?.toFixed(1)}%。` : `Holdings entered ${review.holdings_age_days} days ago; ${review.unallocated_pct?.toFixed(1)}% unallocated.`}</p>
        {review.warnings?.length ? review.warnings.map(w => <p key={w.code + w.subject} className="text-tm-warn">{w.subject}：{w.actual_pct.toFixed(1)}% &gt; {w.limit_pct}% · {zh ? (w.code === "position_limit" ? "超过自设单股上限，请复查" : "超过自设行业上限，请复查") : "Above your cap; review required"}</p>) : <p>{zh ? "已知持仓未超过自设集中度上限。这不等于组合安全或应该买入。" : "Known holdings are within your caps. This does not establish safety or a reason to buy."}</p>}
        <p className="text-tm-muted">{zh ? "行业未知或暂不可核验" : "Unknown sector"}：{review.unknown_sector_tickers?.join(", ") || "—"}。{zh ? "不包含 ETF 穿透与持仓相关性分析。" : "ETF look-through and correlation are not included."}</p>
      </div> : null}
    </> : null}
  </TmPane>;
}
