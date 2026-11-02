# 模拟仓机器人：接口、数据与 UI 实现约定

2026-11-02 · 设计稿，非已发布 API。主需求见 [PRD](../PRD-paper-investment-bot.md)。

## 1. 服务边界

```text
现有 /paper UI ─┐
内置 BYOK bot ─┼→ 账户/研究/订单服务 → sim_* 持久账本
未来外部 agent ┘       ↑                  ↑
                 用户身份 + 账户权限    行情适配 + 撮合 + 日估值
```

首版没有外部 API key 的创建/授权界面。HTTP API 供本平台已登录 UI 与受控后台服务使用；内置模型通过白名单工具协议调用同一业务服务，不拿任意 URL、SQL、用户令牌或 BYOK 明文。

每次执行的身份由后端固定为 `{owner_user_id, account_id, run_id}`。模型返回的任何用户/账户标识均不作为授权依据。市场新闻、公司介绍和模型输出都只是数据，不能扩大工具权限。

## 2. 建议接口

以下是待实现契约，响应中不得包含凭据。所有列表有范围、稳定排序及分页上限。

| 方法与路径 | 用途 | 权限与语义 |
| --- | --- | --- |
| `GET /api/paper/accounts` | 列出本人的人类/机器人账户 | 只读，不因查看而自动创建 bot |
| `POST /api/paper/accounts` | 创建机器人账户 | 用户登录；首版每人一个，重复请求复用同一创建结果 |
| `GET /api/paper/accounts/{id}` | 账户摘要、估值质量、持仓 | 必须验证 owner |
| `GET /api/paper/accounts/{id}/capabilities` | 可执行动作、资金/数量限制、撮合模式、市场状态 | 后端实时计算，不把模型偏好当硬限制 |
| `GET /api/paper/accounts/{id}/context` | 账户、挂单、推荐及记忆的一致输入 | 返回 context_id、配置版本、各来源时间；避免前端拼装不一致状态 |
| `GET /api/paper/instruments?q=&cursor=` | 平台支持的 ticker 搜索与可用性 | 批量上限；返回 instrument_id，ticker 不是永久身份 |
| `GET /api/paper/market-context?instrument_ids=` | 行情与已存在的研究证据 | 有界列表；数据不足返回原因，不触发全市场抓取 |
| `GET/PATCH /api/paper/accounts/{id}/bot` | 读取/修改 bot 配置 | 仅账户主人；配置版本化，不由 bot 自行修改 |
| `POST /api/paper/accounts/{id}/runs` | 手动唤起 | 返回 `202 + run_id`，不是交易成功；重复请求返回同一在途 run |
| `GET /api/paper/accounts/{id}/runs?cursor=` | 运行历史 | 默认 5 条，最近在前 |
| `GET /api/paper/accounts/{id}/runs/{run_id}` | 进度、决策摘要、动作结果、模型用量 | 必须同时校验 run 归属与账户归属 |
| `POST /api/paper/accounts/{id}/runs/{run_id}/stop` | 停止本轮后续动作 | 不回滚已成交，返回已停止与已提交的实际数量 |
| `GET /api/paper/accounts/{id}/orders` | 当前账户订单 | 保留状态、成交时间、来源 run 与执行模式 |
| `POST /api/paper/accounts/{id}/orders` | 共享订单服务入口 | human 账户仅人类；bot 账户仅合法 active run，不允许普通 UI 随意插单 |
| `DELETE /api/paper/accounts/{id}/orders/{order_id}` | 请求撤销可撤订单 | 不撤销成交；可能返回待核对，不伪装立即成功 |
| `GET /api/paper/accounts/{id}/equity-curve` | 净值、基准与估值质量 | 附交易日、价格时间、缺价标记与费用口径 |

原有无 account_id 的 `/api/paper/account`、`/order`、`/orders`、`/reset` 等继续绑定 human 账户。`/picks?ticker=...` 携带选股进入模拟仓时也默认人类视图，不误切 bot。

平台已有推荐/研究查询应提取复用服务或扩展现有契约，而非维护两套计算。API 名称可随实现调整，但数据语义和权限不能变。

## 3. 工具与决策协议

已有 LLMClient 不保证所有 provider 原生 function calling 一致。首版使用严格 JSON 工具协议或统一适配层，保留所选模型，不用“只支持某模型”回避接入问题。

只读工具：`get_account`、`get_open_orders`、`search_instruments`、`get_recommendations`、`get_market_context`、`get_position_memory`。变更工具：`submit_actions`、`cancel_order`、`save_position_summary`。后端决定工具是否当前可用。

建议动作包：

```json
{
  "context_id": "server-issued-context-id",
  "decision": "rebalance",
  "summary": "简短、可供用户阅读的理由，不是内部思维过程",
  "actions": [
    {
      "action_id": "a1",
      "type": "set_target_weight",
      "instrument_id": "server-issued-instrument-id",
      "target_weight": 0.08,
      "evidence_ids": ["server-issued-evidence-id"],
      "reason": "相对现有仓位的调整依据"
    }
  ],
  "position_notes": []
}
```

示例只表示结构，不是真实标的或投资建议。`decision=no_trade` 可有空 actions。模型优先输出目标权重；服务端计算整数股、费用余量、当前持仓与未成交订单的差额。目标权重不能自动补齐成满仓，未分配部分保留现金。

只读补查最多两轮，之后必须收敛为最终动作或明确“不足以决策”。工具错误返回结构化原因，不能无限“再试一次”。输入输出体积、token 与调用次数均有上限。

提交时检查 context 与配置是否仍有效。修改配置、暂停、账户变化或市场闭市后，不直接执行旧动作。少量可修正格式问题可给模型一次修正机会；非法数量、未知标的或越权不是可悄悄补默认值的字段。

## 4. 最小数据改动

| 对象 | 建议新增/调整 |
| --- | --- |
| `sim_account` | `kind=human/bot`、`name`、`status`；用明确账户约束替代唯一 user_id，首版限制一人一类一账户 |
| `sim_bot_config` | account_id、显式 provider/model 引用、策略说明、时间偏移、运行开关、调用预算、范围限制、config_version |
| `sim_bot_run` | account_id、触发来源、计划/实际时间、交易日、状态/阶段、context 与配置快照、精简结果、用量、错误、执行 lease |
| 标的身份注册表 | 若现有元数据没有稳定标识，新增小型注册表，记录内部 instrument_id、交易所、代码有效期及已核验公司行动关系；不能把 CIK 或 ticker 单独当成永久证券身份 |
| `sim_order` | bot_run_id、action_id、accepted_at、execution_model、expires_at、filled_at、quote/bar evidence、滑点与费用版本 |
| `sim_position` 或关联摘要 | instrument_id/稳定身份、简短持仓理由、最后复核 run；现金与持仓仍由账本决定 |
| `sim_equity_daily` | 正确 market_session、估值时间、缺价与数据质量、成本口径；不因没有订单而跳过 |

只增加实际查询需要的索引，例如 `(account_id, created_at desc)`、有效运行的部分索引与订单 `(run_id, action_id)` 唯一约束。状态/动作记录在同一短事务提交；不在等模型或行情时持有数据库锁。

迁移兼容顺序：所有旧账户标为 human → 完成所有入口的显式账户解析 → 添加 bot 新结构与约束 → 才启用创建。回滚先停 bot 入口/调度，不删除新增账户与账本。不能回滚到把 `SELECT ... WHERE user_id` 当成唯一账户的旧代码。

详细诊断有界保留，成交和余额事实长期保留；先量出每 run 行大小/索引增量，再决定保留策略。不照搬旧注释里未经本功能实测的容量估计。

## 5. 调度与状态

独立区分：账户存在、定时启用、当前 run 状态、订单状态。机器人不是“运行结束就销毁”的对象。

```text
run: queued → gathering → deciding → validating → executing → completed
                                                ├→ completed_no_trade
                                                ├→ partial
                                                ├→ skipped
                                                ├→ failed
                                                └→ stopped

order: accepted → pending_market_data → filled
                                 ├→ expired
                                 ├→ rejected
                                 └→ cancel_requested → cancelled / filled
```

run 的 completed 仅表示本轮流程结束；若仍有待成交订单，必须在结果中单列，不暗示全部成交。可以用独立 `stage` 字段表达 gathering 等细阶段，避免在数据库维护过多互斥顶层状态。

调度唯一标识为 `account + trading_session + slot + schedule_version`。修改配置不应让同日已执行时段再次交易；schedule_version 变化后由规则显式决定下一可用 slot，而非简单重新插入当天所有任务。

初版优先复用现有 GitHub runner/后端任务模式。按交易日历算相对开/收市时刻，在普通与半日市的少量候选窗口检查 due accounts，不做全年每分钟轮询。GitHub cron 只是唤起载体，业务判断始终依据当前时间与日历；遗漏和延迟在 UI 可见。[调度限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

每账户一轮在途，worker 使用有期限的 claim/lease。恢复先读已提交动作与订单，不能再次调用模型后把同一笔交易重做。若模型请求结果未知但尚未落库，明确标记可能额外模型用量；不能宣称跨网络调用实现 exactly-once。

Kimi 等慢模型的单次调用使用 provider-aware 时限，必须短于实际平台上限并留持久化余量；多轮拆成多个可恢复阶段。现有 Kimi client 的 read timeout 为 260 秒，这是代码现状，不是所有模型会在该时间内完成的保证。超出实际承载能力时报告运行环境需求，不暗中搬运密钥或降级模型。

## 6. 分钟撮合的必要约定

- 每个 bot 订单固定 `execution_model=intraday_next_bar_v1`。人类旧单保持原模式，两个 cohort 不回溯改写。
- 成交 bar 必须完整，开始时间严格晚于 accepted_at，属于允许交易时段，使用原始未复权价格。保存 bar 起止和取得时间，若延迟取得则先 pending，绝不提前宣称已成交。
- 选择最早合格 bar，不按结果挑更有利的分钟；价格及费用计算由程序完成，模型不能指定自己的成交价。
- 初始实验滑点建议 5 bps：买入参考价上调、卖出下调；成交金额再计 10 bps 费用。三者分别保留 reference_price、fill_price、fee，不重复扣滑点。参数可配置，未声称是现实成本测量结果。
- 收盘前运行必须预留决策和至少一个有效分钟的时间。临近闭市或运行超时后未提交的动作失效，不转为次日盲执行。
- 当合格 bar 已经过但数据尚未抵达，取消请求不能删除可能已经应成交的事实：记录 cancel_requested，按 bar 时间与取消时间先后处理。取消发生在合格 bar 之前可取消；已满足成交条件则记录实际 filled。
- 任一依赖链中先卖后买，买单只使用已实际释放现金。部分成交/失败保留事实，不对整个 run 做伪原子回滚。
- 首版不模拟流动性、排队和复杂订单。若这一执行模式的数据覆盖不达标，明确阻止该模式上线，不偷偷换用旧日线模式。
- 估值与撮合分离；净值日期是对应美股交易日，不直接用跑 cron 的 UTC 自然日。基准使用同日和同回报口径。
- 拆股、分红和代码变更必须有明确处理或异常标记；原始/复权行情不能混用。不明资产事件可冻结单标的，不能擅自把旧 ticker 换成另一家公司。

## 7. 前端实现切片

| 现有组件/位置 | 拟改动 |
| --- | --- |
| `PaperScreen` | 用 SegmentedTabs 切换 human/bot，URL 保留账户选择，分别加载数据，阻止旧请求覆盖新账户 |
| `WorkbenchHeader` | bot 下显示模型/状态/下次唤起，主按钮立即唤起；刷新为次级 |
| `PaperRecommendations`、`SimOrderForm` | 人类视图原样保留，不为 bot 展示可误点的人工票据 |
| 新 `PaperBotRunPane` | 在现有双栏中展示运行阶段、决策摘要与动作，不新建卡片风格 |
| 新 `PaperBotConfigDrawer` | 复用 TmDrawer 和 TM fields，配置模型、时间与预算；保存不重置账户 |
| `PaperPositionsWithSource` | 加入 bot 来源/持仓理由入口；未知归因继续明确未知 |
| `PaperCurvePane` | 按账户查询，保留缺数状态，加口径/模型版本标记；不捏造回报 |
| `PaperOrdersPane` 与新 run ledger | 共用 TmTable/TmPagination，默认五行；详情在抽屉内而非不断展开长列表 |

账户切换时各 query key 都含 account_id，选择中和 loading 状态不可沿用另一账户数值。后台运行不靠组件 mount；页面仅在有活动 run 时有限轮询，后台标签页暂停轮询。

### 设计原则复核

| 原则 | 本次落点 |
| --- | --- |
| 意图对齐 | PaperScreen 明确人类/机器人账户，不先问用户操作一堆模式 |
| 认知负担 | bot 首屏只有账户、当前决策、下一唤起；历史与诊断按需查看 |
| 状态可见 | PaperBotRunPane 区分生成、受理、等待数据、成交 |
| 可恢复 | 配置/行情错误就地恢复；暂停不清仓；局部重试不重复成交 |
| 可供性 | 立即唤起真的运行，配置真的保存，未实现功能不放假按钮 |
| 设计服务任务 | 人类视图保留票据，bot 视图展示决策和运行，不放无用聊天框 |
| 无需说明书 | 账户切换、立即唤起、下次时间可直接理解 |
| 尊重时间 | 入队及时反馈，关闭页面仍运行；分页与详情抽屉避免长页 |
| 不误导 | 不交易是成功结果；过期数据不当即时价格；未知费用不伪精确 |
| 单一主操作 | WorkbenchHeader 的立即唤起为唯一填色主按钮 |
| 可追踪性 | 订单 → run → context/证据时间可追溯，理由不冒充事实因果 |

### 横向约定

- 保留 `AppShell`、`TmScreen`、现有侧栏路由与字体；不引入新的页面壳或装饰性动画库。
- 沿用语义 `--tm-*` 色彩与 12px 最小文字；金额 tabular-nums；运行中不等于收益为正。
- 新文案进入 `sim.accounts.*`、`sim.bot.*` 等现有 i18n 体系；中文不暴露 `RUN.STATUS` 一类内部标识。
- TmDrawer 保留 Escape、焦点陷阱与关闭后焦点返回；tabs 保留方向键；表格有文字状态而非仅颜色。
- 既有控件不改原子资产；新增“持续 bot 运行”作为操作模式补进 `/reference` 与资产目录，先证明实际页面可用，再推广。
- 验收基准为现有生产模拟仓的同页面布局，桌面 1672×941，并检查约 1100px 时的表格边界；不以孤立的概念图代替浏览器验证。

## 8. 依据

核验日期：2026-11-02。工程依据为当前 main 的代码，不代表已验证这些后台路径当前所有线上运行均成功。

- `alpha_agent/api/routes/paper.py`、`alpha_agent/paper/fill_engine.py`、`alpha_agent/api/routes/cron_routes.py`。
- `alpha_agent/storage/migrations/V036__sim_paper_trading.sql`、`V039__paper_p1_provenance_and_cohorts.sql`。
- `alpha_agent/api/byok.py`、`alpha_agent/llm/base.py`、`alpha_agent/llm/_legacy/kimi.py`、`alpha_agent/storage/propose_jobs.py`。
- `alpha_agent/data/minute_price.py`、`alpha_agent/data/us_provider.py`，含现有分钟缓存与自动复权路径，不能未经适配用作原始盘中成交。
- `frontend/src/components/picks/paper/`、`frontend/src/components/ui/SegmentedTabs.tsx`、`frontend/src/components/tm/`。
- [Master Design System](ALPHA-WORKSTATION-MASTER.md)、[资产目录](ALPHA-DESIGN-SYSTEM-ASSET-CATALOG.md)、[本轮已上线人工模拟仓精修](2026-11-02-paper-refinement.md)。
