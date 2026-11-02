# Paper bot UI handoff

2026-11-02 · 独立前端 session，代码留在 `codex/alpha-paper-bot-plan`，未提交。

## 已实现的切片

- `PaperScreen` 以现有 `SegmentedTabs` 切换 `?account=human|bot`。默认 human，`?account=bot` 可直接载入。切到 bot 时清理人工 ticker；人工推荐、票据、取消和重置仍走旧 API。
- bot 账户列表只读，不因查看而创建。创建 drawer 使用现有 BYOK 的 provider/model 元数据，不读取或要求用户重新填写 key。创建后 PATCH 配置；若 PATCH 失败保留已创建 id，重试不重复创建。创建与定时默认关闭，不会自动唤起。
- bot 两栏：左侧本轮摘要、实际动作、持仓；右侧运行面板、定时暂停/启用、停止本轮、净值。手动运行与定时开关分开，机器人没有人工下单、撤单或重置入口。
- queued/running 才以约 5 秒间隔查单个 run；隐藏标签页暂停，返回立即续查，终态刷新账户和账本。任务不依赖页面存在。请求清理和组件按账户隔离，旧账户响应不能更新新视图；停轮／配置动作会使旧轮询失效。
- runs 和 orders 均用后端 limit/offset 分页，每页 5 条，使用真实 total。状态、详情、模型用量有中英文本；阶段含 gathering/deciding/researching/validating/executing/settling/valuing，未知 stage 退回运行状态文案。
- 决策、订单详情复用 `TmDrawer`。订单展示受理／成交时间、参考价、费用、滑点，并可按 bot_run_id 查看来源运行；原始执行证据仅在诊断折叠中显示。
- 持仓标为“机器人账户归属”，不凭旧 pick/manual 归因推断自主交易。未知来源、行情、费用及请求失败保持缺失状态。
- 账户／持仓／曲线已跟随 nullable 估值契约。缺价时账户净值、未实现盈亏与收益显示 `—`，现金仍可见；曲线保留 null 点，`connectNulls={false}`，不将 null 除以本金变为 0。全缺估值与真正无记录分别显示。
- 保留 AlphaCore 壳、字体与 TM 组件。新增局部 140ms opacity 淡入，尊重 reduced motion，无位移或数值动画。

## 修改范围

新增：`PaperBotScreen.tsx`、`PaperBotConfigDrawer.tsx`、`PaperBotUi.tsx`、`paper-bot.css`、`lib/api/paper-bot.ts`。

扩展：`PaperScreen`、`PaperOrdersPane`、`PaperPositionsWithSource`、`PaperCurvePane`、`PaperOverviewPane`、`lib/api/paper.ts` 及 i18n 文案。没有更改共享 TM 原子资产。

主 session 后续要求 nullable formatter/graph 同步后，最小必要地扩展了原先目录边界：`frontend/src/lib/paper-curve.ts` 处理 null gap，`frontend/src/components/picks/SimPositionRow.tsx` 防止 null `.toFixed`／`Math.abs`。人工数值响应的既有展示逻辑保持相同。

## 检查与当前限制

- 主 session 随后明确授权串行完整构建与 light smoke。`NODE_OPTIONS=--max-old-space-size=768 npm run build` 成功，设计系统／路由语言／token 审计均通过，Next 15.5.25 生成 23 个静态页面；`/paper` 为动态路由，页面代码 19.4 kB，First Load JS 329 kB。产物在 `frontend/.next/`。
- 构建中出现现有 jose CompressionStream／DecompressionStream 的 Edge Runtime 警告。本次唯一 ref cleanup lint 提示已在构建后修正，随后对全部相关组件执行 targeted `next lint`：零 warnings/errors。
- 最终当前源码 `tsc --noEmit --incremental false` 通过；`git diff --check -- frontend` 通过。串行运行 2 个相关测试文件，共 10 项通过，涵盖原人工流程的静态渲染、缺失行情不伪造 bot 盈亏、bot 不显示人工撤单按钮、null 曲线保留日期断点。未将 static markup 称为浏览器验收。
- 没有运行开发服务器、浏览器、安装依赖、真实 API 写入或 BYOK 调用；没有开启任何 bot、push、merge 或 deploy。
- build 前 preflight 为 constrained，内存压力 2、swap 约 12.72 GiB、磁盘可用约 31.27 GiB；构建、类型检查和 smoke 均串行。复用已有 `alpha-llm-reliability/frontend/node_modules`，没有安装依赖。为便于主 session 继续本地渲染验收，保留临时 `frontend/node_modules` symlink 与 `.next` 产物；所有者移交主 session，验收结束后可删除链接和生成产物，不删除所指向的现有依赖。
- 构建额外生成的 `frontend/alpha-llm-reliability/` tracing 副本已按确切清单移除 31 个生成 JS 文件／链接及空目录；未触碰依赖原件。部署应由主 session 从当前源码正常重建，不直接分发复用外部 node_modules 的本地 standalone 副本。
- 浏览器任务与中英／深浅主题、1672×941／1100px 的运行时视觉验收仍需主 session 完成；静态检查不是视觉接受。也未声称实际队列、撮合或模型闭环成功。

## 接口核对点

- 前端遵循发来的稳定路径与 limit/offset 合同，没有调用初稿中未承诺的 capabilities/context 接口。
- 已按当前 `BotConfig` 收紧至固定两次 30 分钟时段、每日最多 12 次、最多 20 持仓、model 120 字符、instructions 2000 字符。
- 当前 runner 的 `result={decision, actions, settlement?}` 已可展示 recorded actions；动作状态仍表示受理／拒绝／保持等原始事实，最终成交以订单表为准，不能因 run completed 便解释为全部成交。
- types 已包含后端追加的 nullable 账户／持仓／曲线／归因盈亏、估值质量／时间与订单执行字段。`PaperAttributionTable` 与 `PaperSourceSummary` 也会将缺失归因盈亏显示为 `—`，不把 null 加作 0。未知 result 形状只在详情诊断中可查，不生成假动作或金额。
- 尚未将每只持仓的长期理由接到表格，因为稳定账户响应没有提供 thesis/position-note 字段；运行 drawer 已将该轮 decision.position_notes 显示为“本轮持仓复核”，并将实际动作按 action_id 对上该轮模型理由。若希望逐持仓显示长期理由，应由后端提供明确字段后接入，不能用最近一轮摘要冒充该持仓的原因。
