"use client";

import { useState } from "react";
import { apiGet, apiPost, ApiException } from "@/lib/api/client";
import { useLocale } from "@/components/layout/LocaleProvider";
import { TmPane } from "@/components/tm/TmPane";
import { TmButton, TmLinkButton } from "@/components/tm/TmButton";
import { TmInput, TmSelect, TmTextarea } from "@/components/tm/TmField";

type Entry = { ticker: string; rationale: string; counterevidence: string; invalidation: string; source_notes: string; next_review: string; status: string; revision: number; updated_at?: string; review_due?: boolean };
const blank = (ticker = ""): Entry => ({ ticker, rationale: "", counterevidence: "", invalidation: "", source_notes: "", next_review: "", status: "watch", revision: 0 });

export default function InvestmentNotebook({ ticker }: { ticker?: string }) {
  const { locale } = useLocale(); const zh = locale === "zh";
  const [open, setOpen] = useState(false); const [busy, setBusy] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]); const [draft, setDraft] = useState<Entry>(blank(ticker));
  const [error, setError] = useState(""); const [saved, setSaved] = useState(false); const [loaded, setLoaded] = useState(false);
  const fail = (e: unknown) => setError(e instanceof ApiException && e.status === 401
    ? (zh ? "请先登录，再保存你的私人研究记录。" : "Sign in to save your private research.")
    : e instanceof ApiException && e.status === 409
      ? (zh ? "记录已在其他页面修改，或已达到 30 个股票上限。请重新加载后检查。" : "Record changed elsewhere or the 30-ticker limit was reached. Reload and review.")
      : (zh ? "无法读取或保存，请重试并检查必填项。" : "Unable to load or save. Retry and check required fields."));
  const load = async () => {
    setOpen(true); setBusy(true); setError(""); setSaved(false);
    try {
      const data = await apiGet<{ entries: Entry[] }>("/api/user/investment/theses");
      setEntries(data.entries); setDraft(data.entries.find(e => e.ticker === ticker) ?? blank(ticker)); setLoaded(true);
    } catch(e) { setLoaded(false); fail(e); } finally { setBusy(false); }
  };
  const edit = (key: keyof Entry) => (value: string) => { setDraft(d => ({ ...d, [key]: value })); setSaved(false); };
  const select = (value: string) => { setDraft(entries.find(e => e.ticker === value) ?? blank(ticker)); setSaved(false); };
  const save = async () => {
    setBusy(true); setError(""); setSaved(false);
    try {
      const { ticker: symbol, rationale, counterevidence, invalidation, source_notes, next_review, status, revision } = draft;
      const { entry } = await apiPost<{ entry: Entry }, object>("/api/user/investment/theses", { ticker: symbol, rationale, counterevidence, invalidation, source_notes, next_review, status, revision });
      setDraft(entry); setEntries(old => [...old.filter(e => e.ticker !== entry.ticker), entry]); setSaved(true);
    } catch(e) { fail(e); } finally { setBusy(false); }
  };
  return <TmPane title={zh ? "投资理由与复查记录" : "Investment thesis and review"} bodyClassName="gap-3 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-tm-muted">{zh ? "为什么关注，什么证据会让你改变判断？先记下来，允许继续观察、不操作。" : "Why follow this stock, and what would change your mind? Record it; watching without trading is valid."}</p>
      <TmButton variant="secondary" loading={busy} aria-expanded={open} onClick={() => open ? setOpen(false) : void load()}>{open ? (zh ? "收起" : "Collapse") : (zh ? "打开研究记录" : "Open notebook")}</TmButton>
    </div>
    {open ? <>
      {error ? <div role="alert" className="flex flex-wrap items-center gap-3 text-xs text-tm-neg">{error}<TmButton variant="secondary" onClick={() => void load()}>{zh ? "重新加载" : "Reload"}</TmButton></div> : null}
      {loaded ? <>
        {!ticker ? <TmSelect label={zh ? "复查队列，最多 30 个股票" : "Review queue, up to 30 tickers"} value={draft.revision ? draft.ticker : ""} onChange={select} options={[{value: "", label: zh ? "新建记录" : "New entry"}, ...entries.map(e => ({value: e.ticker, label: `${e.ticker} · ${e.next_review}${e.review_due ? (zh ? " · 到期复查" : " · Review due") : ""}`}))]} /> : null}
        <div className="grid gap-3 md:grid-cols-3">
          <TmInput label={zh ? "股票代码" : "Ticker"} value={draft.ticker} disabled={!!ticker || draft.revision > 0} onChange={value => edit("ticker")(value.toUpperCase().trim())} />
          <TmInput type="date" label={zh ? "下次复查日期" : "Next review"} value={draft.next_review} onChange={edit("next_review")} />
          <TmSelect label={zh ? "研究状态，不是交易指令" : "Research status, not an order"} value={draft.status} onChange={edit("status")} options={[{value: "watch", label: zh ? "继续观察，不操作" : "Watch, no action"}, {value: "review", label: zh ? "需要复查" : "Review required"}, {value: "closed", label: zh ? "结束跟踪" : "Stop tracking"}]} />
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <TmTextarea rows={3} maxLength={1000} label={zh ? "关注或持有理由" : "Rationale"} value={draft.rationale} onChange={edit("rationale")} />
          <TmTextarea rows={3} maxLength={1000} label={zh ? "反面证据与风险" : "Counterevidence and risks"} value={draft.counterevidence} onChange={edit("counterevidence")} />
          <TmTextarea rows={3} maxLength={1000} label={zh ? "什么条件使判断失效" : "Invalidation conditions"} value={draft.invalidation} onChange={edit("invalidation")} />
          <TmTextarea rows={3} maxLength={1000} label={zh ? "信息来源、日期及待核实事项" : "Sources, dates and unverified claims"} value={draft.source_notes} onChange={edit("source_notes")} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <TmButton variant="secondary" loading={busy} disabled={!draft.ticker || !draft.next_review || !draft.rationale.trim() || !draft.counterevidence.trim() || !draft.invalidation.trim() || !draft.source_notes.trim()} onClick={() => void save()}>{zh ? "保存研究记录" : "Save research"}</TmButton>
          {draft.ticker ? <TmLinkButton href={`/stock/${encodeURIComponent(draft.ticker)}`}>{zh ? "核对股票事实" : "Check stock evidence"}</TmLinkButton> : null}
          {saved ? <span role="status" className="text-xs text-tm-pos">{zh ? "已保存，不会创建交易。" : "Saved. No trade created."}</span> : null}
        </div>
        <p className="text-xs text-tm-muted">{zh ? "这是你填写的观点，不是已验证的事实。日期到期会在队列内提示，但不自动监测事件、发通知或止损；当前仅保留每个股票的最新记录。" : "User-authored views, not verified facts. Due dates appear in the queue; no event monitoring, notifications or stop orders. Only the latest record per ticker is retained."}</p>
      </> : null}
    </> : null}
  </TmPane>;
}
