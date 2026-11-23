"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import { useLocale } from "@/components/layout/LocaleProvider";
import { useAdminAccess } from "@/components/layout/SystemHealth";
import { TmCheckbox, TmInput, TmSelect } from "@/components/tm/TmField";
import { TmTable, TmTableHead, TmTableBody, TmTableRow, TmTableHeaderCell, TmTableRowHeader, TmTableCell } from "@/components/tm/TmTable";
import { TmButton, TmDisclosureButton } from "@/components/tm/TmButton";
import { apiGet, ApiException } from "@/lib/api/client";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";

function Fold({title,children}:{title:string;children:ReactNode}) {
  const [open,setOpen]=useState(false), id=useId();
  return <section><TmDisclosureButton label={title} expanded={open} aria-controls={id} onClick={()=>setOpen(!open)}/>
    <div id={id} hidden={!open} className="max-h-[42vh] space-y-3 overflow-y-auto overscroll-contain px-4 py-3 text-sm">{open&&children}</div></section>;
}

function Read<T>({path,children}:{path:string;children:(value:T)=>ReactNode}) {
  const {locale}=useLocale(), zh=locale==="zh";
  const [result,setResult]=useState<{path:string;data?:T;error?:number}>();
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    let active=true;
    setResult(undefined);
    apiGet<T>(path).then(data=>{if(active)setResult({path,data});}).catch(e=>{
      if(active)setResult({path,error:e instanceof ApiException?e.status:0});
    });return ()=>{active=false;};
  },[path,retry]);
  if(result?.path!==path)return <p role="status">{zh?"正在读取记录…":"Loading records…"}</p>;
  if(result.error!==undefined)return <div role="status" className="flex items-center gap-3">
    {result.error===401||result.error===403?(zh?"请使用有查看权限的账户登录。":"Sign in with access to these records."):(zh?"记录暂时不可读取。":"Records are unavailable.")}
    <TmButton variant="secondary" onClick={()=>setRetry(n=>n+1)}>{zh?"重试":"Retry"}</TmButton></div>;
  return <>{result.data && children(result.data)}</>;
}

type Move={ticker_return:number;spy_return:number;excess_return:number};
type Reaction={status:string;gap:Move|null;follow_through:Move|null;timing:string};
type EventRow={id:string|number;ticker:string;title:string;source:string;url:string;status:string;published_at:string|null;published_date?:string|null;first_seen_at:string;reaction?:Reaction|null};
type Events={events:EventRow[];coverage:{status:string;sources:{source:string;ticker:string;status:string}[]}};
const names:Record<string,string>={observed:"已记录",corrected:"已更正",withdrawn:"已撤回",healthy:"正常",stale:"过期",unsupported:"未覆盖",unavailable:"不可用",not_checked:"未检查",partial:"部分覆盖",not_sampled:"尚未采样",disabled:"未启用",credentials_missing:"未配置数据凭据",not_started:"尚未启动",awaiting_borrow_evidence:"等待借券证据",insufficient:"样本不足",sec_edgar:"SEC 公告",investor_relations:"公司公告",indicative:"指示价",future:"时标异常",no_fresh_reference:"无有效现货参考价",no_contracts:"无符合条件的合约",coverage_truncated:"覆盖不完整",provider_unavailable:"来源不可用",long_only:"仅做多",long_short:"多空",no_trade:"不交易",pending:"等待",closed:"已平仓",open:"已开仓",expired:"已过期",abstained:"不参与"};
const trialReasons:Record<string,string>={no_trade_control:"不交易对照组",not_unambiguous_issuer_disclosure:"不是明确的发行人披露",no_explicit_guidance_revision:"未明确上调或下调业绩指引",long_only_no_short:"仅多组不开空",unverified_issuer_release_time:"公告发布时间未核实",old_release_discovered_after_policy_window:"发现时已超过反应窗口",awaiting_fresh_regular_bar:"等待常规时段的新鲜行情",regular_session_closed:"常规交易时段已结束",awaiting_corporate_action_evidence:"公司行动资料不齐",awaiting_borrow_carry_evidence:"借券计息证据不全",cash_margin_or_volume_limit:"现金、保证金或成交量限制",open_position_limit:"已达到持仓上限",issuer_raises_guidance:"发行人上调业绩指引",issuer_lowers_guidance:"发行人下调业绩指引",planned_exit:"按原计划平仓"};
const label=(v:string,zh:boolean)=>zh?names[v]??trialReasons[v]??v.replaceAll("_"," "):v.replaceAll("_"," ");
const usd=(v?:number|null)=>v==null?"—":v.toLocaleString("en-US",{style:"currency",currency:"USD",maximumFractionDigits:2});

export function EventInbox(){
  const {locale}=useLocale(),zh=locale==="zh";const {timeZone}=useTimezonePreference();
  const [symbol,setSymbol]=useState(""),[filter,setFilter]=useState("");
  const stamp=(s:string)=>new Date(s).toLocaleString(zh?"zh-CN":"en-US",{timeZone,timeZoneName:"short",month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
  return <Fold title={zh?"重大事件与来源覆盖":"Material events & source coverage"}>
    <form className="flex items-center gap-2" onSubmit={e=>{e.preventDefault();setFilter(symbol.trim().toUpperCase());}}>
      <TmInput className="w-40" aria-label={zh?"股票代码":"Ticker"} placeholder={zh?"全部代码":"All tickers"} maxLength={10} value={symbol} onChange={setSymbol}/>
      <TmButton type="submit" variant="secondary">{zh?"筛选":"Filter"}</TmButton></form>
    <Read<Events> path={"/api/alerts/events?limit=10"+(filter?"&ticker="+encodeURIComponent(filter):"")}>{d=><>
      <p className="text-tm-muted">{zh?"来源覆盖：":"Coverage: "}{label(d.coverage.status,zh)}</p>
      {!d.events.length&&<p>{zh?"此范围尚无事件记录，不代表市场没有事件。":"No events recorded in this scope. This does not mean none occurred."}</p>}
      <ol className="divide-y divide-tm-rule">{d.events.map(e=><li className="space-y-1 py-2" key={e.source+":"+e.id}>
        <strong>{e.ticker}</strong>{" · "}{/^https?:\/\//i.test(e.url)?<a className="text-tm-accent underline" href={e.url} target="_blank" rel="noreferrer">{e.title}</a>:e.title}
        <div className="text-tm-muted">{label(e.source,zh)} · {label(e.status,zh)} · {zh?"公布":"Published"} {e.published_at?stamp(e.published_at):e.published_date??"—"} · {zh?"首次收到":"First seen"} {stamp(e.first_seen_at)}</div>
        {e.reaction&&<p>{zh?"开盘跳空（非策略收益）":"Opening gap (not strategy P&L)"} {pct(e.reaction.gap?.ticker_return)} · {zh?"可观察后 30 分钟相对 SPY":"Next observable 30m vs SPY"} {pct(e.reaction.follow_through?.excess_return)} · {label(e.reaction.status,zh)}</p>}</li>)}</ol>
      {!!d.coverage.sources.length&&<details><summary className="cursor-pointer">{zh?"查看各来源状态":"Inspect source checks"}</summary>
        <div className="max-h-40 overflow-y-auto py-2">{d.coverage.sources.map(s=><div key={s.source+s.ticker}>{s.ticker} · {label(s.source,zh)} · {label(s.status,zh)}</div>)}</div></details>}
    </>}</Read></Fold>;
}

type Attr={window:{start_date:string;end_date:string;status:string};coverage:{filled:number;trade_attribution:number;terminal_marks:number;terminal_marks_required:number};totals:{fees:number|null;slippage_usd:number|null;net_vs_hold_usd:number|null};scenarios:Record<string,{nav:number|null}>;trades:{order_id:number;ticker:string;side:string;qty:number;fee:number|null;net_vs_hold_usd:number|null}[]};
type Options={status:string;samples:{status:string;received_at:string;sample:{contracts?:{contract:string;bid:number|null;ask:number|null;oi:number|null;iv:number|null;quality:string}[]}}[]};
const pct=(n:number|null|undefined)=>n==null?"—":(n*100).toFixed(2)+"%";
export function BotResearch({id}:{id:number}){
  const {locale}=useLocale(),zh=locale==="zh",admin=useAdminAccess();
  const [symbol,setSymbol]=useState("NVDA"),[historic,setHistoric]=useState(false);
  return <>
    <Fold title={zh?"换手归因：换股比原仓不动好吗？":"Turnover attribution: trade or hold?"}>
      <TmCheckbox checked={historic} onChange={setHistoric} label={zh?"复盘 2026 年 11 月 10 至 23 日":"Replay November 10–23, 2026"}/>
      <Read<Attr> path={`/api/paper/accounts/${id}/bot/turnover-attribution${historic?"?start_date=2026-11-10&end_date=2026-11-23":""}`}>{a=><>
        <p>{a.window.start_date} → {a.window.end_date} · {a.coverage.filled} {zh?"笔成交":"fills"} · {a.window.status==="pending_close"?(zh?"待收盘":"Waiting for close"):a.window.status==="complete"?(zh?"完整":"Complete"):(zh?"证据不全":"Partial evidence")}</p>
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[[zh?"实际净值":"Actual NAV",a.scenarios.actual?.nav],[zh?"原仓不动":"Hold opening book",a.scenarios.hold?.nav],[zh?"仅减风险":"Reduce only",a.scenarios.reduce_only?.nav],[zh?"相对不动的增益":"Value vs hold",a.totals.net_vs_hold_usd]].map(([k,v])=><div key={String(k)}><dt className="text-tm-muted">{k}</dt><dd>{usd(v as number|null)}</dd></div>)}</dl>
        <p>{zh?"手续费":"Fees"} {usd(a.totals.fees)} · {zh?"可观测滑点":"Observable slippage"} {usd(a.totals.slippage_usd)}</p>
        <details><summary className="cursor-pointer">{zh?"逐笔相对持有的贡献":"Per-fill contribution vs hold"}</summary>
          <div className="max-h-60 overflow-auto"><TmTable className="w-full text-left"><TmTableHead><TmTableRow>{(zh?["代码","方向","股数","手续费","相对持有"]:["Ticker","Side","Shares","Fee","Vs hold"]).map(h=><TmTableHeaderCell key={h}>{h}</TmTableHeaderCell>)}</TmTableRow></TmTableHead>
          <TmTableBody>{a.trades.map(t=><TmTableRow key={t.order_id}><TmTableCell>{t.ticker}</TmTableCell><TmTableCell>{zh?(t.side==="buy"?"买":"卖"):t.side}</TmTableCell><TmTableCell>{t.qty}</TmTableCell><TmTableCell>{usd(t.fee)}</TmTableCell><TmTableCell>{usd(t.net_vs_hold_usd)}</TmTableCell></TmTableRow>)}</TmTableBody></TmTable></div></details>
        <p className="text-tm-muted">{zh?"期末行情覆盖":"Terminal price coverage"} {a.coverage.terminal_marks}/{a.coverage.terminal_marks_required} · {zh?"可归因成交":"Attributed fills"} {a.coverage.trade_attribution}/{a.coverage.filled} · {zh?"缺失估值不补零；滑点已含在成交价内。":"Missing marks are not zero; fill prices include slippage."}</p>
      </>}</Read>
    {historic && <Fold title={zh?"查看最近完整收盘日的核验 · 11 月 20 日":"Verified replay through the last full close · November 20"}>
      <Read<{status:string;metrics?:{filled:number;fees:number;actual_nav:number;hold_nav:number;reduce_only_nav:number;actual_vs_hold:number};recorded_at?:string}> path={`/api/paper/accounts/${id}/bot/turnover-replay?start_date=2026-11-10&end_date=2026-11-20`}>{r=>r.metrics?<><p>{zh?"事后用同一批期末价格重估，不是当时的交易输入。":"Revalued after the fact with matched terminal marks, not contemporaneous trading evidence."}</p>
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[[zh?"实际交易":"Actual",r.metrics.actual_nav],[zh?"原仓不动":"Hold",r.metrics.hold_nav],[zh?"仅减仓":"Reduce only",r.metrics.reduce_only_nav],[zh?"相对不动":"Actual vs hold",r.metrics.actual_vs_hold]].map(([k,v])=><div key={String(k)}><dt>{k}</dt><dd>{usd(v as number)}</dd></div>)}</dl>
        <p>{r.metrics.filled} {zh?"笔成交，费用":"fills · fees"} {usd(r.metrics.fees)} · {zh?"口径：与原账本一致，不含现金分红。":"Original ledger basis, excluding cash dividends."}</p></>:<p>{zh?"本账户没有这段时间已核验的复盘。":"No verified replay for this account and period."}</p>}</Read></Fold>}</Fold>
    {admin&&<><ShadowResearch zh={zh}/>
      <Fold title={zh?"私人期权观察 · 不交易":"Private option observations · no trades"}>
        <TmSelect label={zh?"标的":"Underlying"} value={symbol} onChange={setSymbol} options={["NVDA","SPY","QQQ"].map(value=>({value,label:value}))}/>
        <Read<Options> path={`/api/research/option-observations?symbol=${symbol}`}>{o=><>
          <p>{label(o.status,zh)} · {zh?"免费派生指示价，不是可成交报价。":"Free indicative feed, not executable quotes."}</p>
          {o.samples.map(s=><div key={s.received_at}><p>{s.received_at} · {label(s.status,zh)}</p>
            {s.sample.contracts?.map(c=><p key={c.contract} className="border-t border-tm-rule py-1">{c.contract} · {usd(c.bid)} / {usd(c.ask)} · IV {c.iv==null?"—":(c.iv*100).toFixed(1)+"%"} · OI {c.oi??"—"} · {label(c.quality,zh)}</p>)}</div>)}
        </>}</Read></Fold></>}
  </>;
}

function ShadowResearch({zh}:{zh:boolean}){
  return <Fold title={zh?"股票事件影子账户 · 与模拟仓隔离":"Stock event shadow books · separate ledger"}>
    <Read<{status:string;books:Record<string,{free_cash:number;open_count:number;closed_count:number}>;trials:{ticker:string;sleeve:string;status:string;reason:string}[];review:{review_eligible:boolean;observed_sessions:number;paired_event_clusters:number;metrics:Record<string,{return:number|null;max_sampled_drawdown:number|null;fees:number;worst_trade_usd:number|null}>}}> path="/api/research/event-shadow">{d=><>
      <p>{d.status==="collecting"?(zh?"已启用":"Active"):(zh?"尚未开始":"Not activated")} · {zh?"仅在常规交易时段模拟成交，不动现有持仓。":"Regular-session simulation only; existing positions are unchanged."}</p>
      {!!Object.keys(d.books).length&&<TmTable className="w-full text-left tabular-nums"><TmTableHead><TmTableRow>{(zh?["对照组","可用现金","持仓数","已平仓数"]:["Book","Available cash","Open","Closed"]).map(h=><TmTableHeaderCell key={h} scope="col">{h}</TmTableHeaderCell>)}</TmTableRow></TmTableHead>
        <TmTableBody>{["no_trade","long_only","long_short"].filter(k=>d.books[k]).map(k=><TmTableRow key={k} className="border-t border-tm-rule"><TmTableRowHeader>{label(k,zh)}</TmTableRowHeader><TmTableCell>{usd(d.books[k].free_cash)}</TmTableCell><TmTableCell>{d.books[k].open_count}</TmTableCell><TmTableCell>{d.books[k].closed_count}</TmTableCell></TmTableRow>)}</TmTableBody></TmTable>}
      <p>{d.review.review_eligible?(zh?"已达到首次评审门槛":"Ready for first review"):(zh?"仍在积累前向证据":"Collecting forward evidence")} · {d.review.observed_sessions}/20 {zh?"个可比交易日":"comparable sessions"} · {d.review.paired_event_clusters}/30 {zh?"个配对事件":"paired events"}</p>
      {Object.entries(d.review.metrics).map(([key,m])=><p key={key}>{label(key,zh)} · {zh?"净收益":"Net return"} {m.return==null?"—":(100*m.return).toFixed(2)+"%"} · {zh?"采样最大回撤":"Sampled drawdown"} {m.max_sampled_drawdown==null?"—":(100*m.max_sampled_drawdown).toFixed(2)+"%"} · {zh?"费用":"Fees"} {usd(m.fees)}</p>)}
      {!d.trials.length?<p>{zh?"尚无前向试验记录。":"No forward trials recorded yet."}</p>:d.trials.map((r,i)=><p key={i}>{r.ticker} · {label(r.sleeve,zh)} · {label(r.status,zh)} · {label(r.reason,zh)}</p>)}
    </>}</Read></Fold>;
}

export function RunEventEvidence({accountId,runId}:{accountId:number;runId:string}){
  const {locale}=useLocale(),zh=locale==="zh";
  const captions:Record<string,string>={review_risk_reduction:"减仓另行复核",review_rating_change:"有评级变化，仍须复核",unchanged:"持仓不变",insufficient_evidence:"证据不足",withhold_unproven_replacement:"影子规则不增加仓位：缺少新增证据"};
  return <Read<{context_available:boolean;seen_event_ids:string[];shadow_events_known_by_then:{ticker:string;title:string}[];actions:{ticker:string;disposition:string}[]}> path={`/api/paper/accounts/${accountId}/runs/${runId}/event-evidence`}>{r=><div className="space-y-2 border-y border-tm-rule py-3">
    {!r.context_available?<p>{zh?"本轮未留下决策上下文。":"No decision context was recorded."}</p>:<>
    <p>{zh?"模型实际收到的官方事件：":"Official events actually in model input: "}{r.seen_event_ids.length}</p>
    <p className="text-tm-muted">{zh?"以下是当时影子库已收到的事件，不代表模型读过。":"Known to the shadow feed by decision time; not necessarily seen by the model."}</p>
    {r.shadow_events_known_by_then.length?r.shadow_events_known_by_then.map((e,i)=><p key={i}>{e.ticker} · {e.title}</p>):<p>{zh?"没有可核实的同期记录。":"No contemporaneous evidence."}</p>}
    {r.actions.map((a,i)=><p key={i}>{a.ticker} · {zh?captions[a.disposition]??a.disposition:a.disposition.replaceAll("_"," ")}</p>)}</>}
  </div>}</Read>;
}
