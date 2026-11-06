# 机器人只读指标契约

`GET /api/paper/accounts/{id}/bot/performance` 调用 `bot_analytics.read_performance`。使用同一只读 repeatable-read 快照，先校验 owner 与 bot 类型，不抓行情、不调用模型、不写入账本。

| 字段 | 口径 |
| --- | --- |
| `account_id`, `cohort_id`, `as_of` | 账户、当前 reset cohort、UTC 读取时间 |
| `history` | 当前 cohort 最近最多 366 条日记录；多读一条仅判断 `truncated`。`valid_nav_count` 仅统计可证实的有效收盘 NAV，`null_nav_count` 统计实际 null，`incomplete_nav_count` 还包括盘中或其他不合格记录。`first_date`、`last_date` 是读取范围，不是完整 lifetime |
| `valuation` | 同一快照的现金与最多 20 个持仓；复用现有 mark freshness 规则。缺价、过时或公司行动阻断不以成本价或现金冒充 NAV。`exposure_pct = invested_value / NAV * 100`；零 NAV 无比例分母 |
| `matched_window` | 至少两条 NAV 与 SPY 都有效的共同收盘观察，以相同首尾日期计算 bot、SPY、cash 收益。`sample_count` 是共同观察数。`complete` 要求期间每个真实 XNYS session 都有合格共同观察；缺口不抹平，仍可算端点收益，但最大回撤为 null |
| `orders` | 当前 cohort 的实际 filled、pending、failed、expired、cancelled 数与 filled `transaction_cost` 合计。数据库没有 rejected 状态，因此 `rejected` 为 null，不把 failed 改名成 rejected |
| `turnover` | 同一比较窗口 `(首日收盘, 末日收盘]` 的双边 gross filled notional，除以完整日路径 NAV 算术平均值，乘 100。不除以二、不年化。成交时间或价格不明、日路径缺口、比较不足时比例为 null |
| `llm` | 账户 lifetime 内最近最多 20 个 run 的已持久化 token 与调用数，不混称当前 cohort 或 lifetime 总用量。`first_run_at`、`last_run_at` 标出范围。默认零与失败记录可能遗漏服务商未报告用量；没有已核定定价，`cost_usd` 为 null，不是零 |
| `comparators` | SPY 是原始价格参考，不含股息、交易费用或可交易模拟账本。cash 为零利息零费用参考。确定性策略尚无有效模拟账本，`available=false`、`return_pct=null`，不借用研究账户或虚构历史等权收益 |

所有 `*_pct` 均使用百分点，例如 `1.2` 表示 `1.2%`。最大回撤是非负的峰谷跌幅，且仅代表所示窗口的日收盘路径，不代表盘中最大回撤。bot NAV 已包含实际交易费用，不重复扣费。无年化或 Sharpe。

历史记录需 `valuation_quality` 为 `session_close` 或 `cash_only`，且 `valued_at >= 当日实际收盘时间`、该交易日已收盘。盘中数值即使后来变成历史日，也不自动视为收盘数据；cash-only 的 SPY 同样需要该证据。数据不足、日路径不完整、日历不可用分别返回 `insufficient_common_observations`、`incomplete_daily_path`、`exchange_calendar_unavailable`。当前读到的最近日记录或旧窗口不声称实时、完整或自账户创建起的收益。

验证边界：窄范围纯计算与 mock 用例由主任务串行执行；不以 mock 证明真实数据库迁移、行情质量、生产 API 或页面验收。
