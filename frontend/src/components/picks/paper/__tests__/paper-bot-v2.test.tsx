import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { canWakePaperBot, type PaperBotConfig, type PaperBotPerformance, type PaperBotRun } from "@/lib/api/paper-bot";
import { PaperBotActions, PaperBotOutcome, PaperBotExecutionSummary, botReason } from "../PaperBotUi";
import { PaperBotReadiness, PaperBotPerformanceSummary } from "../PaperBotEvidence";
import PaperPositionsWithSource from "../PaperPositionsWithSource";

const config: PaperBotConfig={account_id:7,provider:"kimi",model:"saved-model",instructions:"",schedule_enabled:false,open_enabled:true,close_enabled:true,open_offset_minutes:30,close_offset_minutes:30,max_daily_runs:6,max_positions:8,max_position_weight:0.25,fee_bps:10,slippage_bps:5,config_version:2,credential_configured:true,next_wake_at:null,market:{session_date:"2026-11-06",is_open:true,open_at:null,close_at:null,next_open_at:null},readiness:{evaluated_at:"2026-11-06T15:00:00Z",can_wake:true,blocked_reasons:[],warnings:["research_stale"],schedule_reason:"schedule_disabled",today_runs:1,research_as_of:null,research_age_sessions:null}};
const run: PaperBotRun={id:"r1",account_id:7,status:"no_trade",stage:null,trigger:"manual",created_at:"2026-11-05T12:00:00Z",started_at:null,finished_at:null,summary:null,error:null,result:{actions:[],outcome_reason:"market_closed"},prompt_tokens:null,completion_tokens:null,provider:null,model:null};
const performance: PaperBotPerformance={account_id:7,cohort_id:1,as_of:"2026-11-06T15:00:00Z",history:{scope:"current_cohort_recent_366",sample_count:1,valid_nav_count:0,null_nav_count:1,first_date:"2026-11-05",last_date:"2026-11-05",truncated:false},valuation:{cash:100000,portfolio_value:null,invested_value:null,exposure_pct:null,quality:"partial",valued_at:null},matched_window:{start_date:null,end_date:null,sample_count:0,expected_sessions:0,missing_sessions:0,complete:false,bot_return_pct:null,spy_return_pct:null,cash_return_pct:null,bot_max_drawdown_pct:null,reason:"insufficient_common_observations"},orders:{scope:"current_cohort",filled:0,pending:0,failed:0,expired:0,cancelled:0,paid_fees:0},turnover:{window_start:null,window_end:null,gross_filled_notional:null,average_nav:null,ratio_pct:null,reason:"insufficient_common_observations"},llm:{scope:"recent_20_runs_account_lifetime",run_count:1,prompt_tokens:null,completion_tokens:null,cost_usd:null,cost_reason:"provider_pricing_unavailable"},comparators:{spy:{basis:"raw_price_no_dividends"},cash:{basis:"zero_interest"},deterministic:{available:false,reason:"no_simulated_ledger"}}};

describe("paper bot v2 evidence boundaries",()=>{
  it("labels stale bot marks as dated snapshots without changing human labels",()=>{
    const positions=[{ticker:"TEST",qty:10,avg_cost:9,current_price:10,unrealized_pnl:10,unrealized_pct:11.11,price_quality:"stale",mark_at:"2026-11-06T20:31:00Z"}];
    const bot=renderToStaticMarkup(<PaperPositionsWithSource positions={positions} attribution={[]} accountKind="bot" />);
    expect(bot).toContain("快照市值");
    expect(bot).toContain("快照浮盈亏");
    expect(bot).toContain("报价已过期");
    expect(bot).toContain("04:31");
    expect(bot).not.toContain("当前市值");
    const missing=renderToStaticMarkup(<PaperPositionsWithSource positions={[{...positions[0],current_price:null,mark_at:null}]} attribution={[]} accountKind="bot" />);
    expect(missing).not.toContain("$100");
    expect(missing).not.toContain("Invalid Date");
    const human=renderToStaticMarkup(<PaperPositionsWithSource positions={positions} attribution={[]} />);
    expect(human).toContain("当前市值");
    expect(human).not.toContain("报价已过期");
  });
  it("summarizes only server-confirmed ledger facts, retaining unknown fees",()=>{
    const planned={...run,result:{actions:[{ticker:"ABC",status:"accepted"}]}};
    expect(renderToStaticMarkup(<PaperBotExecutionSummary run={planned} />)).toContain("尚未核验");
    const result=renderToStaticMarkup(<PaperBotExecutionSummary run={{...planned,order_summary:{total:2,filled:1,pending:1,failed:0,expired:0,cancelled:0,filled_notional:100,paid_fees:null}}} />);
    expect(result).toContain("实际订单");
    expect(result).toContain("已成交");
    expect(result).not.toContain("$0.00");
  });

  it("paginates long drawer actions instead of growing the page",()=>{
    const many={...run,result:{actions:Array.from({length:8},(_,index)=>({action_id:`a${index}`,ticker:`SYMBOL${index}`,status:"accepted"}))}};
    const second=renderToStaticMarkup(<PaperBotActions run={many} page={2} />);
    expect(second).toContain("SYMBOL7");
    expect(second).not.toContain("SYMBOL4");
  });
  it("separates current readiness from paused scheduling, historical market state and research warnings",()=>{
    expect(canWakePaperBot(config)).toBe(true);
    const current=renderToStaticMarkup(<PaperBotReadiness config={config} />);
    expect(current).toContain("可手动唤起");
    expect(current).toContain("定时暂停不影响手动唤起");
    expect(current).toContain("研究证据已超过配置的新鲜度");
    expect(current).not.toContain("暂不可唤起");
    const historical=renderToStaticMarkup(<PaperBotOutcome run={run} />);
    expect(historical).toContain("当前不在交易时段");
    expect(historical).toContain("不代表成交，也不代表策略验证通过");
    expect(canWakePaperBot({...config,readiness:{...config.readiness!,can_wake:false,blocked_reasons:["market_closed"]}})).toBe(false);
  });

  it("keeps unknown readiness and research age unknown for older responses",()=>{
    const markup=renderToStaticMarkup(<PaperBotReadiness config={{...config,readiness:undefined}} />);
    expect(markup).toContain("尚未核验");
    expect(markup).not.toContain("可手动唤起");
    expect(canWakePaperBot({...config,readiness:undefined})).toBe(true);
    expect(canWakePaperBot({...config,credential_configured:false})).toBe(false);
  });

  it("shows action acceptance and actual expired or filled order status as different facts",()=>{
    const result={actions:[{action_id:"a1",ticker:"TEST",status:"accepted",order_status:"expired"},{action_id:"a2",ticker:"TEST2",status:"accepted",order_status:"filled",filled_at:"2026-11-06T15:05:00Z",filled_price:10,fee:0.05}]};
    const markup=renderToStaticMarkup(<PaperBotActions run={{...run,result}} />);
    expect(markup).toContain("动作结果");
    expect(markup).toContain("已受理");
    expect(markup).toContain("订单现状");
    expect(markup).toContain("已到期");
    expect(markup).toContain("已成交");
    expect(markup).toContain("$0.05");
    const old=renderToStaticMarkup(<PaperBotActions run={{...run,result:{actions:[{status:"accepted",ticker:"TEST"}]}}} />);
    expect(old).toContain("尚未核验订单现状");
  });

  it("bounds main-screen actions while retaining every action in the drawer variant",()=>{
    const many={...run,result:{actions:Array.from({length:8},(_,index)=>({action_id:`a${index}`,ticker:`SYMBOL${index}`,status:"accepted"}))}};
    const bounded=renderToStaticMarkup(<PaperBotActions run={many} limit={4} />);
    expect(bounded).toContain("显示 4 / 8 条动作");
    expect(bounded).not.toContain("SYMBOL4");
    expect(renderToStaticMarkup(<PaperBotActions run={many} />)).toContain("SYMBOL7");
  });

  it("does not turn missing bot or benchmark metrics into zero returns",()=>{
    const markup=renderToStaticMarkup(<PaperBotPerformanceSummary data={performance} />);
    expect(markup).toContain("同日收盘记录不足");
    expect(markup).not.toContain("0.00%");
    expect(markup).not.toContain("NaN");
    expect(markup).toContain("$0.00");
  });

  it("uses matched endpoints with an explicit gap warning and drawdown magnitude",()=>{
    const data={...performance,matched_window:{...performance.matched_window,complete:true,start_date:"2026-10-01",end_date:"2026-11-05",bot_return_pct:1.2,spy_return_pct:-0.5,cash_return_pct:0,bot_max_drawdown_pct:25}};
    const markup=renderToStaticMarkup(<PaperBotPerformanceSummary data={data} />);
    expect(markup).toContain("+1.20%");
    expect(markup).toContain("-0.50%");
    expect(markup).toContain("25.00%");
    expect(markup).not.toContain("+25.00%");
    const incomplete=renderToStaticMarkup(<PaperBotPerformanceSummary data={{...data,matched_window:{...data.matched_window,complete:false}}} />);
    expect(incomplete).toContain("中间有缺日");
    expect(incomplete).not.toContain("25.00%");
  });

  it("explains concrete no-trade outcomes without treating acceptance as settlement",()=>{
    expect(botReason("zh","keep_cash")).toContain("保留现金");
    expect(botReason("zh","orders_accepted")).toContain("不代表成交");
    expect(botReason("en","model_timeout")).toContain("timed out");
    expect(botReason("zh","future_reason")).toBe("future_reason");
  });
});
