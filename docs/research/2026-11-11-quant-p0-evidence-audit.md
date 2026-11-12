# 交易方法论 P0：证据审计

日期：2026-11-11。范围：路线图 §5 的 1–9；仅离线评估代码和本文件/配套协议。
审阅代码基线为 **8c7d992**（本地main衍生基线，非生产部署证明）；没有调用 cron、bot、LLM、订单、数据库或凭据。
历史 7 月审计及 runbook 只用于定位，不能证明今天的线上行为。

## 结论先行

**Evidence insufficient**。当前不能验证成本后赚钱能力，也不能凭短期亏损判定信号永久无效。
继续自然观察和修复证据链可以进行；晋升策略、扩大风险预算及盈利宣传 **No-go**。
现有账户、融合参数、账本、费用和调度均未修改。

| 严重度 / 分类 | 发现与影响 | 当前源码证据（路径:行） |
| --- | --- | --- |
| P0 / risk，旧证据无效 | PARA 曾发生发行人碰撞，旧 tactical 不能成为收益样本；新 v3 不能与旧曲线拼接。当前窄注册表不等于完整 security master | `alpha_agent/data/security_identity.py:1–23`；`backtest/l2_continuous.py:21–88`；`backtest/l2_driver.py:135–139` |
| P1 / defect | scoreboard 用可覆盖的 fast/slow 信号、D 收盘→下一条行情收益，在已有 D 收盘后发布的信号上不具备可执行性；缺终点的股票先退出排名集合。不能当作 L2 或 bot 收益 | `alpha_agent/backtest/scoreboard.py:143–179`；`ledger.py:52–60` |
| P1 / defect | L2 只在推荐成功发布后自然推进；推荐缺价暂停会同时阻止旧持仓估值/已有订单处理。估值不应依赖产生新决策 | `.github/workflows/cron-shards.yml:439–456`；`alpha_agent/backtest/l2_driver.py:148–175,208–213`；`backtest/l2_daily.py:14–28` |
| P1 / risk | `daily_prices` 只有 ticker/date/close，原地覆盖；没有首次可得时间、价格 vintage、调整因子或发行人 ID。冻结信号不等于冻结收益标签 | `storage/migrations/V011__daily_prices.sql:13–18`；`storage/queries.py:476–492`；`ledger.py:228–239` |
| P1 / defect | scoreboard 换手用股票集合重合度，只扣一次单边成本，未计替换时买+卖，也忽略权重漂移；SPY 缺日与策略累计样本可不同；alpha 使用 gross | `backtest/scoreboard.py:254–275,280–306` |
| P1 / risk | `LEAD(close,h)` 数的是有价格的行，不是 XNYS session；tier、consistency、calibration 可把缺价跨度当 h 日。tier 还未选每个决策时点的唯一 canonical run | `backtest/tier_validation.py:63–77`；`consistency.py:100–127`；`confidence_calibration.py:40–55` |
| P1 / unknown | bot 实际配置/持续净值/费用/公司行动不可从公共接口核验。其 SPY 为 raw price、无分红无费用；不能直接与 adjusted L2 宣称模型增益 | `paper/bot_analytics.py:139–168,223–231`；`paper/intraday.py:24–26` |
| P2 / risk | “股票池”是 prior-UTC-day 选出的约 240 + watchlist，且历史评分 ticker 未与当前 membership 作硬交集；不是全 S&P 500。历史成分表可减少但不能消灭生存者偏差 | `data/research_refresh.py:10–21`；`storage/queries.py:379–426`；`universe.py:30–50`；`ledger.py:154–166` |
| P2 / unknown | `data_asof=input_data_cutoff=as_of` 是聚合时间；没有证明各字段实际可得时间≤决策。snapshot writer 未填 `price_downloaded_at`，也把 `in_universe` 设为 True | `ledger.py:74–102,228–239`；`storage/product_ledger.py:55–73` |

以上无前缀路径均相对于 `alpha_agent/`；`.github/` 与 `scripts/` 相对于仓库。P0=会使业绩证据失效，P1=阻断可执行/可比较结论，P2=必须披露和补证。分类按本次实际看到的证据，而非代码注释自称“causal”。

## 现场复核：只作描述

一次性公开 GET：2026-11-11 **08:56:20–08:56:48 UTC**，四个 HTTP 200。
脚本 `scripts/research/collect_public_evidence.py` 每路只请求一次，无认证、无重试、拒绝重定向。
原始回执仅在 `/tmp/alpha-quant-p0-public-evidence-20261111.json`，未提交生产数据。

| 公共来源 | 本次观察 |
| --- | --- |
| [lean](https://alpha-api.bobbyzhong.com/api/picks/lean) | canonical run **79**，market_date **2026-11-09**，generated_at **2026-11-10 04:44:02.656162 UTC**，cutoff **04:43:29.658597 UTC**；239/240 eligible，stale=True、tradable=False |
| [tactical](https://alpha-api.bobbyzhong.com/api/l2/evidence?sleeve=tactical) | strategy 159 / **v3**，重启原因为 PARA；现金/NAV $1m，0 持仓、**50 overdue**，**0 valuations**，没有可评估的收益路径；0% 不是有技能的结果 |
| [strategic](https://alpha-api.bobbyzhong.com/api/l2/evidence?sleeve=strategic) | strategy 28 / **v2**；2026-08-18→11-09 **−3.6197%**，SPY **−1.7779%**，RSP **+0.8049%**，含初始费用；39 valuations、**20 missing sessions、2 stale sessions**；105 `dead_feed_at_fill`、100 `superseded_by_account_progress`、93 overdue；observed DD **−7.9758%**；mean rebalance turnover **78.0407%**，费用累计 $5,365.91 |
| [scoreboard](https://alpha-api.bobbyzhong.com/api/picks/scoreboard) | 21 个 evaluated days；long hit 50.95%；long gross −1.8572%、net −2.9527%，SPY −1.9121%；其样本/成本/执行定义有上述问题，不能与 strategic 的收益作优劣对比 |

strategic 端点起止日超额约 **−1.84 百分点 vs SPY、−4.42 百分点 vs RSP**，仅为端点描述。
缺历史日不能重建真实完整 DD/vol，`missing_marks=105` 是计数而非 105 个交易日。
mean rebalance turnover 排除了零换手日，不是年换手率（`api/routes/l2.py:118–135`）。
用户提供的“11-10 价格覆盖 85%<95%、GitHub 晚 3.5h”**未由此次四个公共端点独立证实**；源码能确认门槛/暂停机制，精确覆盖和触发时间须查下文 SQL A/G。不得把此前 11-09 bot 的迟到记录当成 11-10 research 事件。
生产部署 SHA 未在这些回执中提供，**unverified**；源码推断不等于已部署缺陷复现。

## 1. 今日目标与风险约束

| 项目 | 已实现/默认值 | 证据与边界 |
| --- | --- | --- |
| 市场 | 美股/ETF、USD，XNYS session 与纽约 DST/提前收市 | `market_session.py:14–57`；`paper/market_clock.py`；不能按 pyproject 中旧 A 股说明推断市场 |
| 研究候选 | membership 最新快照 + VRT 为基础；fast/slow 绝对分数优先，截取 240，再并 watchlist | `universe.py:27–50`；`storage/queries.py:393–426`；`data/research_refresh.py:10–14`。不保证全部候选是今日成分股；当前 run 实见 240 个 |
| L2 两书 | long-only、Top50、BUY/OW 优先再 rank、目标等权，目标单名≤2%，不足50留现金 | `backtest/l2.py:26–67`；strategic 从冻结 `_mode_payloads.long` 读取 `policy_rank/rating`：`l2_continuous.py:131–159` |
| L2 期限/频率 | tactical 融合5日，strategic 融合60日；两个书均默认每≥5个价格表交易日再平衡，D+1 close | `fusion/policy.py:99–119,145–165`；`backtest/l2_driver.py:24,194–204`。信号期限不等于真实持仓期限；5日 cadence 按价格表计数有缺日风险 |
| L2 现金/成本 | $1m 初始，整股、先卖再买、无杠杆、现金约束；单边10bps综合成本；没有额外滑点 | `l2_continuous.py:23,264–297`。2%是目标约束，价格漂移和先计算目标后扣成本可使实际权重偏离；不是持续硬上限 |
| L2 风险预算 | 未见行业上限、组合波动/DD目标、止损预算或硬换手上限 | `l2.py:26–35`、`l2_continuous.py:251–303`。每次允许大额轮换，不能将“weekly”解释为低换手 |
| bot 默认 | 8 持仓、单名25%、horizon_sessions=20、research_age≤3 sessions、daily runs≤6；调整带0、每run gross turnover≤2 NAV；fee10bps+slip5bps | `paper/bot_models.py:12–32`；`bot_execution.py:177–244`。实际配置必须 SQL B；期限是上下文/偏好，不是自动到期清仓规则 |
| bot 可交易范围 | 当前快照 eligible/in_universe 的前20 + 持仓/有限补查；有 instrument_id、fresh raw quote、同标的证据才接受，允许现金和不交易 | `paper/bot_context.py:103–126,152–175`；`bot_execution.py:167–208`。运行次数预算不是交易配额；没有已证实的组合DD/行业风险预算 |

现状目标只能写成：**检验这些既定条件下，相对 SPY 和同候选等权的成本后增量**。
任何新增风险限制/换手带均需新版本、理由、预期影响及测试，不能回写正在运行的参数。

## 2. Point-in-time 链路逐项判定

| 环节 | 判定 / 严重度 | 证据、理由、待证点 |
| --- | --- | --- |
| signal publish | verified-safe（代码契约）/ P2 residual | `ledger.py:52–60,143–149,228–245` 在 session close 后取卡片并冻结；writer 使用事务+日期锁：`storage/product_ledger.py:113–159`。没有逐输入发布时间证明；不能称整条链无lookahead |
| snapshot / corrections | verified-safe 写入、risk 历史查询 / P1 | writer append-only且纠错新run；canonical 取最新 `finished_at`：`product_ledger.py:163–199`。历史重放须取 decision_at 前已发布版本，不能事后最新 correction |
| data availability | unknown / P1 | 字段 cutoff 与聚合asof相同、价格下载时间未填；最新价表可覆盖。PIT fundamentals filing+1日仅对SEC新增行成立：`scripts/refresh_research_dataset.py:74–82`；历史供应商修订 vintage 未证明 |
| executable quote | verified-safe bot / unknown L2 realistic fill | bot接受需5分钟内、当session、raw/source：`bot_execution.py:25–35`；L2只读取D+1日close，不含盘口/流动性，不能假称真实可成交价：`l2_continuous.py:234–241` |
| order acceptance | verified-safe（代码契约）/ P2 residual | bot保存真实 `accepted_at`、config/run/cohort/lease核验、现金预留：`bot_execution.py:66–132,246–265`；模型输出只是target，非订单/成交 |
| next minute fill | verified-safe 时间顺序、risk 缺第一根 / P2 | `intraday.py:135–175` 要start>accepted、完整且已取得、最早可用bar、raw、公司行动阻断。但若最初应有分钟根本缺失，可选择更晚有效bar，不能证明是真正市场“下一根”；需缺分钟回归与明确拒绝规则 |
| d1_close / late runs | verified-safe continuous、defect legacy / P1 | continuous仅现存pending、固定next_XNYS、generated_at<目标收盘；错过创建窗口不造历史目标：`l2_driver.py:148–175,192–204`；`l2_continuous.py:213–228`。允许事后对事先意图用历史close确认模拟fill，非当时已成交证明。legacy `l2_driver.py:97–105` / `l2.py:145–171` 无同样时间护栏 |
| lookahead in labels | defect / P1 | scoreboard的D→下一价收益不可执行；tier/consistency/calibration按有价行LEAD跳缺日。以D+1入场、D+1+h离场重新定义，标签不全保持缺失，不能过滤后重新排名 |
| adjusted vs raw | risk / P1 | daily cron `history(period=...)`未显式固定调整参数：`api/cron/daily_prices.py:51–68`；另一provider显式auto_adjust=True：`data/us_provider.py:124–126`；bundle manifest adjustment=all。bot显式raw。用途分离有保护，但跨路径分红/拆股/版本一致性未证明 |
| corporate actions | unknown / P1 | bot对当天action阻断成交/估值：`intraday.py:164–169`、`bot_valuation.py:148–167`；没有完整股数/分红/合并选择ledger。事后无action的下一天也不能证明旧持仓已完成reconciliation。adjusted单位持股不等于原始股数现金账 |
| delisting / ticker reuse | verified-safe已知PARA阻断，risk其它 / P0 | `security_identity.py:9–23` 只注册PARA。没有退市收益/发行人映射时不得以最后价自动变现、收益补0、改名PSKY；保持unknown/隔离。v3保留前任ID和起始日期，不继承收益 |
| survivorship | risk / P1 | bundled PIT membership按历史日期mask：`data/membership.py:97–126`；但ticker可得历史仍不含所有已消失证券，sector快照广播：`factor_backtest.py:436–454,473–475`。当前候选排名可含旧ticker，`in_universe=True`不是成员资格证明 |
| missing prices / marks | verified-safe显式标记，risk路径 / P1 | continuous缺成交价`dead_feed_at_fill`，旧mark显式carry+stale：`l2_continuous.py:253–263,327–365`、`l2_daily.py:45–65`。carry不是零真实收益；legacy `l2.py:200–224`缺价强制exit并贡献0，会造成偏差，不能纳入干净样本 |
| scheduling | verified-safe bot窗口 / defect L2耦合 | bot20分钟后记missed不补交易：`bot_schedule.py:62–90`；Vercel当前主时钟、GH备用见runbook与`vercel.json:9–13`。不延长窗口、不增加唤起来凑样本 |

`api/performance.py:25–78` 只是请求/DB timing middleware，**不是投资业绩引擎**。
`fusion/normalize.py:14–48`、`fusion/combine.py:58–108`、`fusion/rating.py:72–97`、`fusion/grades.py` 与 `grade_thresholds.py` 的 z/rank/档位/维度阈值均不是收益率；`guarded_weights.py:28–53` 的现有自适应护栏也使“同policy_id”不保证每轮有效权重完全一致。只读分析须保留逐快照breakdown/有效权重，不能仅按策略名合并。

## 3–5. 一致比较、指标与预注册

完整固定日期、40项检验家族、purge/embargo、成本和基线决策见
[冻结协议](2026-11-11-quant-p0-baseline-protocol.md)。当前没有把 public scoreboard 或残缺L2拼成回测。

主要指标必须共同报告：连续NAV、SPY/RSP/现金/eligible EW、端点超额与relative wealth、完整路径DD、年化vol、成交gross notional/NAV换手、费用与滑点拖累、现金/行业/单名/HHI暴露、价格/执行/估值覆盖、日历和有效独立样本长度。命中率只附录，不参与Go条件。
缺任一必要价格或身份即显示缺失，缺口后的端点收益可单独描述，不能当作一日回报送进统计。资金净流入/重置分cohort，不能当盈利。

## 6. 失败分解：分母不因输赢变化

| 分类 | 已有 status/reason（非新增DB枚举） | 统计处置 |
| --- | --- | --- |
| data_missing | research `partial` + `insufficient_price_coverage:*` / `insufficient_input_coverage:*` / `stale_market_date:*` / `no_benchmark`；snapshot `missing_input/partial_signals/stale_signals/price_not_on_market_date`；L2 `unfilled:dead_feed_at_fill`；bot `portfolio_mark_unavailable/fresh_raw_quote_required/awaiting_complete_bar/corporate_action_requires_reconciliation` | 信号机会/调度分母保留；标签unknown，不算hit/0收益；已有持仓若仍有可靠NAV则纳入策略路径 |
| technical_failure | bot run `failed`、`model_timeout/output_truncated/invalid_output/stage_failed`；L2晚意图 `intent_after_execution_close/missed_execution_session/execution_precedes_latest_valuation`；slot `missed:slot_expired/trigger_not_observed`，`blocked:enqueue_failed` | 可靠NAV含实际现金等待/持仓损益；单列可用性损失，不把故障当信号无效或模型主动no_trade |
| risk_rejection | action `rejected:max_position_weight_exceeded/max_positions_exceeded/targets_exceed_total_capital/turnover_budget_exceeded`；`deferred:awaiting_settled_cash/awaiting_settled_position_slot/ticker_has_pending_order`；order `failed:fill_price_exceeds_available_cash/insufficient_position_at_fill` | rejected动作可能根本没有sim_order行，必须联result.actions；保留机会分母，未成交不冒充交易损益 |
| model_no_trade | run `no_trade` + `keep_cash/keep_positions/strategy_no_op`；`evidence_insufficient`细分为主动等待证据，不冒充风险拒绝 | 正常策略行为；含现金或旧持仓收益；不是失败，不需要增加交易 |
| signal_ineffective | **不存在可直接读取的DB reason** | 仅在身份/PIT/执行/成本/完整标签合格后，成本后增量非正或达不到预注册阈值，作为统计结论；不能根据某次no_trade/HTTP200推断 |
| lifecycle / control | `market_closed/config_changed/execution_window_expired`、取消/停止、旧cohort、PARA隔离、`superseded_by_account_progress` | 分开报告原因和版本，不伪装自主不交易；隔离无效曲线而非仅删除亏损。修复后的事实不覆盖旧回执 |

映射源：`run_health.py:79–100`；`ledger.py:90–102,196–201`；`paper/bot_models.py:63–87`；`bot_execution.py:167–244,295–340`；`bot_runner.py:97–162,178–218,235`；`bot_schedule.py:74–90`；迁移V024/V026/V039/V049/V050/V051。
同轮可多标签；汇总时按 data→technical→risk→model 等优先级给一个主因，同时保留所有原码，`no_trade` 且没有真实reason归unknown。总收益仍保留所有可靠自然日，不能只选“成功交易日”。

## 7. LLM 边界

LLM仅提出假设、目标权重、结构化判断和持仓笔记；真实事实来自带时间/来源的snapshot、quote、订单和账本。
`paper/bot_context.py:33–64` 已隔离旧summary并由当前快照计算排名；`bot_runner.py:18–43` 明确旧笔记不是现时事实。
`bot_execution.py:246–265,354–360` 才受理/记成交；action accepted也不等于filled。
排名分/z-score差值无价格收益单位，不能与10/15bps比较作“足以覆盖成本”结论；模型自己说胜率、最佳窗口或盈利也不是统计证据。
本批没有调用模型验证这项提示词能否永远遵守。

## 8–9. 基线与判定

仅选 **eligible等权** 与 **12–1动量long-only Top50**，均为离线待测控制组；来源、确定规则、成本和局限见配套协议。
没有更换线上策略、采用新数据服务或跑新的收益搜索。
至少先有 **252个自然、完整、可比较交易日** 才作一次预定forward评审（不是252笔交易，不保证统计功效）。现 tactical 可计0，故至少再需252；strategic39估值并非39独立且可比干净日，不能直接抵扣本次前瞻配额；bot未知。
精度/功效示例及更长需求详见协议：日超额σ=100bps时，95%单项均值±5bps需要1537个独立日，检出5bps/日（80% power）需3140；40项Bonferroni保守power约6623日。实际相关/高波动会更长，不能承诺一年足够。**不人为增交易数**。

## 待生产权限持有人执行的只读 SQL（全部 unverified）

本批未连接生产。由主agent在既有授权环境执行；每块放在同一个只读事务中，确认服务时间预算后分块取有界结果。
SQL只用当前迁移中已有字段，不要求新表、索引或持久化导出。`$1` 为已授权bot account_id，`$2` 为cohort_id，使用参数绑定；不在报告中公开用户数据。

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '5s';
-- A: 11-10暂停、晚发布与生产代码版本；无run也必须保留这个事实。
SELECT id,scheduled_for_date,status,started_at,finished_at,data_asof,
       input_data_cutoff,code_version,weight_policy_id,health_json
FROM research_run
WHERE run_type='daily_close' AND scheduled_for_date BETWEEN DATE '2026-11-09' AND DATE '2026-11-10'
ORDER BY scheduled_for_date,id LIMIT 30;

-- B: bot的实际配置版本。默认值不能替代此结果；无需读取BYOK字段。
SELECT a.id,a.kind,a.reset_count,a.initial_cash,a.cash,c.config_version,c.updated_at,
       c.config->>'model' AS model,c.config->>'provider' AS provider,
       c.config->>'horizon_sessions' AS horizon_sessions,
       c.config->>'max_positions' AS max_positions,
       c.config->>'max_position_weight' AS max_position_weight,
       c.config->>'max_turnover_weight' AS max_turnover_weight,
       c.config->>'min_trade_weight_delta' AS min_trade_weight_delta,
       c.config->>'fee_bps' AS fee_bps,c.config->>'slippage_bps' AS slippage_bps
FROM sim_account a JOIN sim_bot_config c ON c.account_id=a.id WHERE a.id=$1 AND a.kind='bot';

-- C: snapshot可得性 / 真实股票池；PIT须再与当地保存的成分历史对照。
SELECT rr.id,rr.scheduled_for_date,count(*) AS snapshots,
       count(*) FILTER(WHERE rs.eligible) AS eligible,
       count(*) FILTER(WHERE rs.in_universe) AS in_universe,
       count(*) FILTER(WHERE rs.price_downloaded_at IS NULL) AS missing_download_time,
       count(*) FILTER(WHERE rs.price_downloaded_at>rr.finished_at) AS future_download,
       count(*) FILTER(WHERE rr.input_data_cutoff>rr.finished_at) AS cutoff_after_publish
FROM research_run rr JOIN rating_snapshot rs ON rs.run_id=rr.id
WHERE rr.id IN (78,79) GROUP BY rr.id,rr.scheduled_for_date ORDER BY rr.id;

-- D: L2事件序列；在离线XNYS含提前收市日历上核验generated_at<目标close。
SELECT o.id,o.strategy_id,o.source_run_id,o.signal_date,o.generated_at,
       r.finished_at AS signal_published_at,o.fill_date,o.fill_price,o.status,
       o.exit_reason,o.gross_notional,o.transaction_cost,o.source_policy_id,o.source_sleeve
FROM l2_order o JOIN research_run r ON r.id=o.source_run_id
WHERE o.strategy_id IN (159,28) AND o.signal_date>=DATE '2026-10-01'
ORDER BY o.strategy_id,o.signal_date,o.id LIMIT 1500;

-- E: 拒绝常在result.actions中，不可只数sim_order。
SELECT status,result->>'outcome_reason' AS reason,
       result->'decision'->>'no_trade_reason' AS model_reason,count(*) AS n
FROM sim_bot_run WHERE account_id=$1 AND created_at>='2026-11-02T00:00:00Z'
GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT action->>'status' AS status,action->>'reason' AS reason,count(*) AS n
FROM sim_bot_run r CROSS JOIN LATERAL jsonb_array_elements(
  COALESCE(r.result->'actions','[]'::jsonb)) action
WHERE r.account_id=$1 AND r.created_at>='2026-11-02T00:00:00Z'
GROUP BY 1,2 ORDER BY 1,2;
SELECT status,fail_reason,count(*) AS n FROM sim_order
WHERE account_id=$1 AND cohort_id=$2 GROUP BY 1,2 ORDER BY 1,2;

-- F: bot执行的可得时间和原始价证据。不要误将bar.start当确认时刻。
SELECT id,bot_run_id,status,accepted_at,expires_at,filled_at,
       execution_evidence->>'confirmed_at' AS confirmed_at,
       execution_evidence->'bar'->>'start' AS bar_start,
       execution_evidence->'bar'->>'end' AS bar_end,
       execution_evidence->'bar'->>'fetched_at' AS fetched_at,
       execution_evidence->'bar'->>'price_basis' AS price_basis,
       execution_evidence->'bar'->'corporate_actions' AS corporate_actions,
       qty,reference_price,fill_price,fee_bps,slippage_bps,transaction_cost,fail_reason
FROM sim_order WHERE account_id=$1 AND cohort_id=$2
ORDER BY id DESC LIMIT 200;

-- G: 价格恢复/发布/L2实际到达时间。日志不存在不能自动归因GH内部负载。
SELECT cron_name,started_at,finished_at,ok,error_count,details FROM cron_runs
WHERE started_at BETWEEN '2026-11-10T20:00:00Z' AND '2026-11-11T08:56:00Z'
  AND (cron_name LIKE '%price%' OR cron_name LIKE '%research%'
       OR cron_name LIKE '%publish%' OR cron_name='l2_cycle')
ORDER BY started_at LIMIT 100;

-- H: 已知身份碰撞和价格修订；不同不代表所有差异都是复权，须核对来源。
SELECT strategy_id,status,min(signal_date),max(signal_date),count(*) FROM l2_order
WHERE ticker='PARA' AND signal_date>DATE '2025-08-06' GROUP BY 1,2;
SELECT o.id,o.strategy_id,o.ticker,o.fill_date,o.fill_price,p.close AS revised_close
FROM l2_order o JOIN daily_prices p ON p.ticker=o.ticker AND p.date=o.fill_date
WHERE o.strategy_id IN (159,28) AND o.status='filled'
  AND abs(p.close-o.fill_price)>0.000001 ORDER BY o.id DESC LIMIT 100;

-- I: 固定窗口所有估值行（不先过滤亏损/缺失）；日历由离线XNYS给出。
SELECT strategy_id,as_of_date,nav,cash,market_value,net_return,gross_return,
       turnover,stale_count,missing_count,marked_at
FROM l2_equity_daily WHERE strategy_id IN (159,28)
  AND as_of_date BETWEEN DATE '2026-08-18' AND DATE '2026-11-10'
ORDER BY strategy_id,as_of_date;
SELECT as_of_date,portfolio_value,benchmark_close,valuation_quality,valued_at
FROM sim_equity_daily WHERE account_id=$1 AND cohort_id=$2
  AND as_of_date BETWEEN DATE '2026-11-02' AND DATE '2026-11-10'
ORDER BY as_of_date;
COMMIT;
```

现有schema **无法用SQL补出** daily_prices首次到达/历史版本、完整发行人事件、被删原信号、真实盘口成交或LLM未知美元费用。查询不到不是safe；缺这些仍unverified。
同时必须向主agent核对部署SHA与GH触发时钟元数据，不能由仓库版本或HTTP200代替。

## 建议的下一小切片（仅提案）

1. **L2估值与发布解耦**：不加频率、不补旧决策，已有自然触发即允许旧持仓mark/事先pending处理。预期恢复覆盖、不改善信号。测试：publish失败仍估值；无新intent；缺价/stale保留；原窗口不变。
2. **独立标签/scoreboard契约**：用decision时已发布snapshot、固定XNYS入离场日、完整候选分母、买卖双方成本与共同基准。测试：晚发布/correction/缺下一session/亏损终点/卖出费用；旧指标改为retrospective而非回写历史。
3. **价格/身份最小只读对账**：先取SQL C/F/H/I，区分raw与adjusted；公司行动未解保持隔离。预期让证据失效有原因；未来是否加vintage结构由主agent另评，小切片不能顺便扩DB。
4. **离线基线重放器**：冻结eligible集合、整数股/现金/成本；构建EW与12–1 monthly控制。先用手工toy账验证拆分、缺价、排队、行业暴露；通过后才在既有bundle做明确标成历史诊断的比较。
5. **自然forward归档与只读评审**：保留版本/config/每次原码和数据质量；达到固定评审日统一查看，不提前挑窗口或补单。新参数实验另开协议，不能延长本版本直至显著。

## 本地验证回执

`PYTHONPATH=.`确认`alpha_agent`与`research_eval`均解析到本worktree；指定pytest **23 passed**，指定ruff **All checks passed**。pytest只有仓库既有asyncio fixture loop scope未配置的deprecation warning；没有改全局配置。额外以显式2023-10-30→2027-11-12范围的离线XNYS日历确认前瞻窗口252sessions；现有`market_session`默认日历范围截至2027-11-11，不能用它的默认边界悄悄截掉未来最后一天。未执行数据库测试，故不需要pg_ctl参数。

## 补记（2026-11-11 晚）：生产只读 SQL 结果与因子新鲜度

执行方式：主 agent 用生产库 owner 连接，但每块都在 `REPEATABLE READ READ ONLY` 事务内、`statement_timeout=5s`，查询后回滚；原始结果只留在本机 `/tmp`，不入库、不进 PR。下文只记脱敏结论，不含用户邮箱、账户余额以外的个人数据或任何凭据。

### A–I（审计原 SQL，机器人账户号与 cohort 用子查询自动取）

| 块 | 结论 |
| --- | --- |
| A | 11-05、11-06、11-09 三个市场日各有一个 complete run（#77/#78/#79），均在次日发布；**11-10 没有 run**（推荐暂停），code_version 依次为 `4d54ab4a4c0f`、`651bdaf4c2ea`、`e8caf3d92852`。 |
| B | 机器人账户 1 个（reset_count 0），配置版本 4（11-06 修改），fee 10 + slippage 5 bps，最多 8 只、单只 ≤25%、换手上限 2.0、研究过期上限 3 个交易日，定时开启。模型供应商字段为 openai 兼容，模型 `kimi-for-coding`。 |
| C | #77–#79 各 240 个快照、239 eligible、240 in_universe；**`price_downloaded_at` 全部为空**（原审计 P2 结论成立，快照写入方没有填价格下载时间）；无“数据截止晚于发布”。 |
| D | strategic(28)：397 filled、105 `dead_feed_at_fill`（09-15→09-22 信号）、100 `superseded_by_account_progress`（08-03→08-10）、93 pending（11-09 信号）；tactical(159) 只有 50 个 11-09 pending，尚无成交。没有“信号发布一天后才生成订单”的行。 |
| E | 11-02 以来机器人 8 轮：2 轮 completed/`orders_settled`、4 轮 `keep_positions`、1 轮 `invalid_output` 失败、1 轮 no_trade 无原因；动作 9 accepted + 1 existing；订单 10 笔全部 filled。 |
| F | 10 笔成交均为 `raw_unadjusted` 分钟线价格，fill 在受理后下一分钟 bar，确认时间晚于 bar 结束约 1 分钟；费用按 fee 10 + slip 5 计。 |
| G | 11-10 04:43 UTC 发布 #79（市场日 11-09），04:44 `l2_cycle` 运行；之后 **`l2_cycle` 没有再运行**（QUANT-1 修复，PR #90）。11-10 17:01 的发布请求为同市场日 no-op。`daily_prices` 每晚 8 片均成功，每片跳过 1–5 个已退市代码。 |
| H | PARA 在 strategy 1/27（旧书）有 09-15 成交与 10-30 pending，新书无 PARA；strategy 28 有 162 笔成交价与 `daily_prices` 当前收盘价不同，最大相对差 85%，说明价格表被复权或修订覆盖，**冻结成交价 ≠ 当前价格表**，收益复算必须用账本成交价而不是重新 join 价格表。 |
| I | strategy 28 共 39 个估值点（08-18→11-09），NAV 999,004 → 963,803；missing_count 合计 105，stale_count 为 0。tactical(159) 无估值行。机器人账户 11-02→11-05 全现金、11-06 起有持仓，至 11-10 共 7 个估值点（其中 3 个有持仓）；具体金额属私有账户数据，不写入公开仓库。 |

### J：线上因子表达式（QUANT-0 的直接证据）

- `engine_config` 中 `factor.custom_expression` = `group_neutralize(zscore(ts_zscore(volume,20)),sector)`，**2026-08-19 11:35 UTC 由管理员手动设置**（`config_change_log` #26，source=manual，前值 `rank(ts_mean(returns, 12))`）。5 月以来该键共改过 9 次，其中 5 次来自批准的提案，4 次手动。
- `alpha_agent/signals/factor.py` 只有预设短线表达式读每日行情；自定义表达式读仓库内冻结研究面板，其最后一行是 **2026-10-30**。本地用冻结面板最后一行复算的 NVDA/AAPL/MSFT 因子 z 与线上 `/api/stock/{ticker}` 返回值逐位相同。
- 因此 10-30 之后，因子信号（NVDA 有效权重约 0.52）不随行情更新。本批（PR `codex/factor-signal-freshness`）只做披露：信号 `raw.factor_source` 记录表达式、面板与数据日，详情页因子行显示“自定义表达式 · 冻结研究面板 · 数据截至 2026-10-30”。**表达式本身没有改**；是否改回预设由用户决定，改动须登记协议新版本。
- 同一表达式在研究面板上：扣 10bps 与 100bps 融券后三折 OOS Sharpe −4.12/−6.08/−10.85（均值 −7.02），零成本时 5.20/1.88/−1.89；日均 L1 换手约 2.0。这就是演化页基线 Sharpe −7.01 的来源。

### K：11-02 每日因子循环失败

最后一次运行 11-02 16:52 UTC：GA 一路成功并提了 3 个候选（`adv20`、`adv60`、`normalize(volume)`，均凭 −4.2 的负基线门槛通过）；**失败来自 LLM 一路**——生成 5 个，其中 `lf_robust_zscore` 自定义算子单测失败、`winsorize(...)` 内核报 `Quantiles must be in the range [0, 1]`，按规则 kernel_exception 使整轮 `ok=false`，熔断器随后停用工作流。循环保持停用，恢复条件见优化计划 Session C。

### L：5 日校准置信度为何只有 3 个值

- 11-11 01:45 新拟合的映射只有 95 个样本、4 级；但 #77–#79 快照里的 `confidence` 只有 3 个值（0.3384/0.3718/0.4032），它们来自 **09-26 那版映射**（981 个样本、7 级，含这三档）。11-03 至 11-10 的几次重拟合样本只有 2–40 个、`applied=false`，所以发布时一直沿用 09-26 的旧映射。
- 同时 `daily_signals_fast` 的原始一致度每天有 230+ 个不同值。也就是说，校准把 0.40–0.95 的原始值压成 3 档，且这套映射已经 6 周未更新。详情页（读当前映射）与推荐页（读快照）因此给出不同数值。本批不改校准算法，只在模拟仓表格改用排名分、在详情页注明样本数与档位数（QUANT-4）。

### 可执行看板首次读数（QUANT-2，PR #91，只读）

top 10、21 个快照：评估 20 个区间（08-28 → 11-10），多头毛 −1.00%、双边 10bps 后 −4.89%，同区间 SPY +1.52%；420 个候选中 28 个缺价记 unknown。样本短且重叠，只作描述，结论仍为 **Evidence insufficient**。

## 补记（2026-11-12）：QUANT-0 决定已执行与次日核查

- **QUANT-0 决定**：用户批准把线上因子恢复为预设，并登记协议 v1.1.0（见[冻结协议 · 版本 v1.1.0](2026-11-11-quant-p0-baseline-protocol.md)）。v1.0.0 存档不改。
- **L2 估值与发布解耦（#90）**：11-11 的 23:00 UTC 定时任务直到 11-12 03:33 UTC 才启动，`fast_intraday` 与 `l2_cycle` 均在 Vercel 上 300 秒超时，之后断路器暂停了 cron-shards。重新启用后手动触发 `l2_cycle`，1 秒完成：两本账的 11-09 目标单在 11-10 收盘价成交（strategic 93 条、tactical 50 条），并补记 11-10、11-11 两日净值，stale 为 0。这证明在没有新发布快照的情况下也能估值和成交，#90 的目的达到。上一轮超时的原因未定（同一代码手动运行正常），继续观察。
- **最近使用（#103）**：11-11 15:01 UTC 的机器人运行早于 #103 部署（15:05 UTC），`last_used_at` 仍为 09-05。需等下一次机器人实际调用模型后再核查。
- **factor_source 披露（#94）**：11-11 没有完整研究运行，`daily_signals_slow` 最新是 11-10 的 491 行（早于 #94 部署），尚无 `factor_source` 字段可查。需等下一次完整运行。
