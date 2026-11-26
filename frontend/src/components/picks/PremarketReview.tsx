"use client";

import { useLocale } from "@/components/layout/LocaleProvider";
import { useAdminAccess } from "@/components/layout/SystemHealth";
import { Fold, Read } from "@/components/research/ForwardEvidence";
import { useTimezonePreference } from "@/hooks/useTimezonePreference";

type Evidence = {id:number; ticker:string; title:string; url:string};
type Observation = {
  session_date:string; stage:string; captured_at:string;
  payload:{
    run_id:number|null; comparable:boolean; tracked:number; recent:number; top_covered:number; truncated:boolean;
    context:{ticker:string|null;title:string;url:string|null;source:string;at:string;new:boolean}[];
    notes:{ticker:string;tag:string;held:boolean;in_top:boolean}[];
    changes:{out:string;into:string|null}[];events:Evidence[];new_event_ids?:number[];
    quotes?:Record<string,{price:number;at:string}|null>;
    results?:Record<string,{status:string;delta_bps:number|null}>;
  };
};
export default function PremarketReview(){
  const admin=useAdminAccess(), {locale}=useLocale(), {timeZone}=useTimezonePreference();
  if(!admin)return null;
  const zh=locale==="zh", txt=(cn:string,en:string)=>zh?cn:en;
  const stamp=(s:string)=>new Date(s).toLocaleTimeString(zh?"zh-CN":"en-US",{timeZone,hour:"2-digit",minute:"2-digit",timeZoneName:"short"});
  const reason:Record<string,string>={no_decision:txt("没有可验证的开盘决策","No verified opening decision"),incomplete:txt("证据不足","Incomplete evidence"),too_late:txt("已过可比较时段","Decision too late"),missing_bars:txt("缺少配对行情","Missing paired bars")};
  return <Fold title={txt("盘前复核 · 独立观察","Premarket review · shadow")}>
    <Read<{records:Observation[];summary:{observed_closes:number;stages:Record<string,{measured:number;mean_bps:number|null}>}}> path="/api/research/premarket-review">{({records,summary})=><>
      <p>{txt("正式 Top 50 和机器人不变。只对已监测的官方披露做复核，未发现不代表没有新闻。","Official picks and bot are unchanged. Only monitored official disclosures are covered.")}</p>
      {!records.length&&<p>{txt("尚无自然定时采集的记录。","No scheduled observations yet.")}</p>}
      {summary.observed_closes>0&&<div><strong>{txt("最近收盘记录 · 平均净差（非账户收益）","Recent closes · mean net difference, not account P&L")}</strong>
        {Object.entries(summary.stages).map(([k,s])=><p key={k}>{k==="premarket"?"09:20":"10:00"} ET · {s.mean_bps===null?"—":s.mean_bps+" bp"} · {s.measured}/{summary.observed_closes} {txt("笔可比较","measurable")}</p>)}</div>}
      {records.map(({session_date,stage,captured_at,payload:p})=><section className="space-y-2 border-t border-tm-rule pt-2" key={stage}>
        <h3 className="font-semibold">{session_date} · {stage==="evaluation"?txt("收盘对照","Close comparison"):stage==="premarket"?"09:20 ET":"10:00 ET"} · {stamp(captured_at)}</h3>
        {stage==="evaluation"?<>
          <p>{txt("两组都在观察和决策完成后建仓，并计入收盘退出成本。持有现金的名额可因节省费用产生正净差。","Both baskets enter after observation and decision, with closing exit costs. A cash slot can generate a positive difference through avoided costs.")}</p>
          {!Object.keys(p.results??{}).length&&<p>{txt("缺少当日复核快照，无法比较。","No review snapshots to compare.")}</p>}
          {Object.entries(p.results??{}).map(([k,v])=><p key={k}>{k==="premarket"?"09:20":"10:00"} ET · {v.status==="measured"?txt("相对正式榜，扣费后","Net difference vs baseline")+": "+v.delta_bps+" bp":reason[v.status]}</p>)}
        </>:<>
          <p>{txt("正式快照","Baseline")} {p.run_id?"#"+p.run_id:"—"} · {txt("近 20 分钟有监测更新","Sources updated in 20 min")} {p.recent}/{p.tracked} · Top 50 {p.top_covered}/50
            {p.truncated&&txt(" · 证据超限"," · Evidence limit reached")}</p>
          {p.top_covered === 0 && p.comparable && <p className="text-tm-warn">{txt("候选股来源覆盖为零。此次比较依赖榜外来源的更新，解读净差时请计入这一缺口。","No candidate had recent source coverage. This observation qualified on updates outside the Top 50.")}</p>}
          <p>{!p.comparable?txt("证据不足，本轮不参与收益比较。","Insufficient evidence; excluded."):p.changes.length?
            p.changes.map(c=>c.out+" → "+(c.into??txt("现金","cash"))).join(" · "):txt("影子组合保持正式榜不变。","Shadow basket unchanged.")}</p>
          {p.notes.map(n=><div key={n.ticker}><strong>{n.ticker}</strong> · {n.tag==="risk"?txt("风险上升","Risk increased"):n.tag==="attention"?txt("新增关注","Watch"):txt("需复核","Review")}
            {" · "}{n.in_top?"Top 50":txt("榜外","Outside Top 50")}{n.held&&txt(" · 机器人持仓"," · Bot holding")}
            {p.quotes&&n.ticker in p.quotes&&(" · "+(p.quotes[n.ticker]?"$"+p.quotes[n.ticker]!.price.toFixed(2)+" @ "+stamp(p.quotes[n.ticker]!.at):txt("无新鲜报价","No fresh quote")))}
          </div>)}
          {p.events.map(e=><div key={e.id}>{p.new_event_ids?.includes(e.id)&&txt("新增 · ","New · ")}{e.ticker} · {/^https?:\/\//i.test(e.url)?<a className="text-tm-accent underline" href={e.url} target="_blank" rel="noreferrer">{e.title}</a>:e.title}</div>)}
          {p.context.length>0&&<details><summary>{txt("个股与宏观新闻（仅作背景）","Company and macro headlines (context only)")} · {p.context.length}</summary>
            {p.context.map((n,i)=><p key={i}>{n.new&&txt("新增 · ","New · ")}{n.ticker??txt("市场","Market")} · {stamp(n.at)} · {n.url&&/^https?:\/\//i.test(n.url)?<a className="text-tm-accent underline" href={n.url} target="_blank" rel="noreferrer">{n.title}</a>:n.title}</p>)}</details>}
        </>}
      </section>)}
    </>}</Read>
  </Fold>;
}
