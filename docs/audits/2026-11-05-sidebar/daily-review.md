# 日常、账户与参考页交互审计

审计时间：2026-11-05 23:40 至 23:56 CST 左右。对象为生产 `https://alpha.bobbyzhong.com`，不是当前工作树修改的预览。只写本报告和 coverage，不改源码。页面操作全部经 CUA，生产数据、凭据和设置未保存；未运行模型、交易、计算刷新、机器人或回测。

## 基线与边界

- Chrome 用户1，browser `2`，任务标签 `1395914574`，1710×875，中文深色。英文浅色仅抽查 Guide 后恢复中文深色。
- 保留 AlphaCore 终端式工作台、TM 控件、既有章节与双栏／三栏关系。integrate-design 用于区分工作流、布局和细节问题，不授权重设计。
- 资源预检：memory pressure 2、swap 10.56 GiB、可用磁盘 19.29 GiB。复用现有浏览器、单标签串行，无服务、构建或新依赖。
- 阅读 master design、picks browsing/in-place/scroll、paper、alerts、reference refinement 及相关实现。重复记录按组件／状态分组，下述覆盖不是逐股票或逐新闻的全量验收。
- 租约已交还主代理。原标签在 `/data` 完成 markHandoff 后，因其他协作者无法跨会话接管，按主代理后续指示关闭了仅本任务创建的标签 `1395914574`；用户原有标签未动。数据页只读刷新完成，仍为 568 个成分、96.24% close coverage。
- Coverage 共79个组件／控制状态条目：52通过、3失败、24受阻，58个条目含实际操作或观察验证。计数按分组条目，不是独立 DOM 按钮数；Guide22个主题、dropdown选项和分页状态已在条目内明列。JSON parse 与 task-owned diff whitespace 检查通过。

## 需要处理的问题

### P2：空搜索把未知快照标成“有效”（生产可复现）

路径：`/picks`，战术做多。初始快照 #75、市场日 2026-11-02，页头为“过期”。搜索 `ZZZZNOAUDIT` 并等待结果后，0 条匹配、数据时间“暂无”，但页头“快照：有效”，过期冻结横幅也不再显示。清除搜索后恢复 50 条和“过期”。

预期：空搜索不能为快照提供新鲜度证据。保持既有快照状态，或明确“未确认”，不能用缺失 as_of 推导绿色有效。

证据：`sidebar-audit-daily/picks-empty-valid.jpg`；浏览器快照同时显示“数据时间 暂无”“快照 有效”“没有匹配的股票代码”。来源：`frontend/src/components/picks/PicksBrowser.tsx` 的页头 freshness 推导及 `frontend/src/lib/picks-freshness.ts`。主代理已收到并独立着手修复；本审计不声称该修复已生产验证。

### P2：个股把 5 日校准值写成泛化的历史命中率（生产可复现）

路径：从 `/picks` ERIE 进入 `/stock/ERIE`。推荐证据窗口明确区分：次日历史方向一致度 52%（n=50），以及另一持有期的“5 日校准置信度”34%。同一股票详情侧栏却写“历史方向命中率 34%”，中文 tooltip 写“信号过去 5 个交易日方向预测的实际命中率”，容易被读成最近五天的次日命中率，而不是 5 交易日预测持有期的等渗校准输出。

预期：与推荐页统一写“5 日校准置信度”，tooltip 明确预测持有期、不是回看五日／不是独立实测胜率。不要改动数值或 Kelly 计算。

证据：`sidebar-audit-daily/stock-confidence-label.jpg`。准确来源：`frontend/src/components/stock/RatingBadge.tsx:77` 使用 `rating.hitrate` 和 `rating.hitrate_tooltip`；`frontend/src/lib/i18n.ts:1073`、`:1074` 是中文文案，英文 tooltip 位于 `:2633`。这是一致性／数据语义缺陷，不是数学计算错误的证据。

### P3：分钟明细仅可用鼠标从 canvas 进入（可访问性缺口）

`/stock/ERIE` 点击 2026-11-02 K 线能打开 inline 分钟区域，关闭按钮与 Escape 都有效。canvas 没有可聚焦日期选择入口，打开后没有把焦点转入明细，Escape 后 activeElement 为 BODY。该组件名叫 Drawer，但实际不是 modal，因此不应机械套用 modal focus trap；问题是键盘用户缺少等价入口与定位。

小修建议：在图表旁提供只读日期选择／“查看该日分钟走势”按钮，打开后聚焦明细标题，关闭后返回入口。来源：`frontend/src/components/stock/PriceChart.tsx` 的 `subscribeClick` 与 `IntradayDrawer.tsx:130` 的全局 Escape。未要求本轮扩展为图表重构。

## 已观察到正常的关系

- Picks：战术／战略、做多／做空切换有待更新状态；10／25／50 条、第二页及末页维持总量；ERIE 证据窗口、HOLD 补充、关闭／Escape／焦点返回正常。投资计划与研究记录可展开，客户端 select 可切换，未保存。
- Human paper：空仓、零订单真实呈现；过期推荐禁用五个“选择”和下单表单。重置只进入二次确认并取消；“查看下单区”聚焦对应区域。来源、系统验证、两种净值策略、账本异常均可展开。
- Bot paper：已有一轮“不交易”，只读查看本轮和历史行详情；Escape／关闭与焦点返回正常。配置抽屉服务商五项、日程草稿 checkbox、持仓／费用限制展开可达，未保存。运行和订单分页只有 1／0 条，前后页正确禁用。
- Alerts：载入 50 条，需处理10／关注7／仅记录33／已处理0；全部严重性、六种关联对象可切换。需处理第二页、仅记录第七页、J 选择、空搜索、清除筛选均正常；空结果清除详情。处理记录为0真实呈现。未保存本地视图，未 resolve／snooze。
- Guide：六章 22 主题逐一点击，文章标题匹配；跨章 `self-correlation` 搜到 GOOD 主题；空搜索准确；清除搜索恢复原“当前不要误以为已完成的能力”并回焦搜索框。英文浅色可读，已恢复。
- Data：覆盖四组、最低覆盖列表末页（47条／8页）、名册全部板块13项含全部、NVDA／空搜索及第36页（568条）正常。算子52已实现／68注册、操作数45已实现／201注册；算子全部层级切换、两目录第二／末页、代表性 abs／adv10 disclosure 正常。根横纵额外溢出均0。只读刷新保留旧数据并显示更新状态，完成后恢复。

## 明确缺口

不交易、不保存、不制造记录。过期推荐阻止下单票据、clear-selection、买卖／市限价的生产交互；无持仓／订单阻止行详情、撤单和分页。Bot 无订单，不执行唤起、启用日程、停止或保存。Alerts 无处理历史，不能验证 undo／历史行跳转；这些状态不能借生成生产记录补齐。

股票只测 ERIE；分钟区域验证开关，未等待或重试历史分钟数据结论，无当日新闻，未测新闻分析。LLM rich brief、8 个 persona、区间分析均为即时执行，安全阻止。只读 turnover comparison 虽 GET，但会按需 replay，按“不得计算”限制未点。外链／手册跨研究模块链接仅核对目标，交由对应路由审计，避免扩大浏览器租约。

只读 refresh 的入口和加载反馈已观察；Data 的终态已观察，human/bot/alerts 刷新后离页，最终网络终态不列为已通过。未作完整多视口／多语言矩阵、hover 全量、网络失败注入或用户视觉接受。

## 工件

Coverage：`daily-coverage.json`。截图目录：`/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-daily/`，包含 picks-empty-valid、stock-confidence-label、guide-en-light、data-coverage-open、alerts-dark-baseline。后者捕获只读刷新反馈，不是稳定队列的完整基线。
