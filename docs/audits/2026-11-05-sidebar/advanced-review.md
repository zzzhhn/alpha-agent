# 高级与参考页面交互审计

准备日期：2026-11-05。生产浏览器验证：2026-11-06，约 00:14 至 00:28，UTC+8。页面：`/factors`、`/evolution`、`/brain`、`/methodology`、`/reference`；`/settings` 延后。

## 审计边界

保留现有 TM 工作台身份、页面骨架、真实金融证据与既有研究流程。审计控件打开后的任务流、布局、滚动、键盘与状态语义，不做源代码修改。预定边界是不执行计算、提交、批准、凭据操作或持久化设置变更；实际发生一次误判的 Zoo 回测交接自动运行，详情见下方事故记录，不能将本轮描述为完全无副作用。

复用现有 Chrome「用户1」，只新建一个任务页 `1395914582`，已关闭。1710×931，中文／深色；Design System 浮层短暂抽查英文／浅色后恢复。资源预检：memory pressure 2、swap 10.52 GiB、空闲磁盘 19.05 GiB；没有并行服务、构建、安装或额外浏览器。没有部署或触碰真实凭据。

基线：`ALPHA-WORKSTATION-MASTER.md`，2026-11-03 advanced/reference refinement，integrate-design。旧审计仅用来定位当前合同，不作为本轮运行验证。

## 源码确认的问题与安全发现

1. **P1，Settings 入口无操作即覆盖后端关注列表镜像。** 审计基线中，`/settings` 的五个分区使用 `hidden`，并非条件挂载，因此打开页面时即挂载 `WatchlistEditor`，它在 `useEffect` 中调用 `syncWatchlistRemote(initial)`。该 API 是替换语义的 `POST /api/watchlist`，不是只读拉取。新浏览器为空或旧本地列表可能覆盖远端镜像，影响后续 cron 观察范围。预期：读设置页面不应替换关注列表，只有明确添加／移除才触发写入。最小修复：删除挂载推送，保留显式 add/remove 双写。基线证据：`frontend/src/app/(dashboard)/settings/page.tsx:374`，`frontend/src/components/settings/WatchlistEditor.tsx:22`，`frontend/src/lib/api/watchlist.ts:16`。这是源码确认，不是本轮线上请求复现。主审随后通知已在任务源码移除挂载推送，生产尚未更新；本审计仍不进入生产 Settings，实际交互留待修复版验收。
2. `/factors` 初始化会调用 `seedZooIfFirstRun()`，首次访问可能写本地示例。该副作用需要与线上真实状态分开记录。证据：`frontend/src/app/(dashboard)/factors/page.tsx:254`。

## 浏览器确认的问题

### P2，长选择菜单的键盘活动项不会滚动到可见区域

- 路由：`/brain`，1710×931，中文／深色。
- 复现：打开「选择挖矿家族」，按 End。
- 实际：活动项已是「拼接(passer×近失)」，菜单 `scrollTop=0`；活动行 y=495 至 523，而菜单底边 y=500，末项被裁切。键盘选择状态与可见内容脱节。
- 预期：End／连续方向键移动后，当前活动项保持完整可见。
- 最小兼容修复：在活动项改变时仅滚动菜单内部至可见范围，保留现有 portal 与 TM 视觉样式。主审已独立修复任务源码，本轮仅确认生产基线，未验证修复版。
- 证据：`brain-family-end-clipped.jpg`；`frontend/src/components/tm/TmSelectMenu.tsx:211`。

### P2 候选，旧运行的候选审计没有可达入口

- 实际页面显示 162 轮，但「选择挖矿运行」仅提供 #155 至 #162 与跨运行兼容结果。兼容结果能访问 1720 条仿真结果，不等于旧运行候选账本。
- 影响：无法从可见选择器选择 #154 及更旧运行，因此也无法打开其 run-scoped 候选审计。
- 最小兼容方向：保留最近八轮默认密度，增加只读载入更多／运行分页；不要用跨运行结果替代候选审计。是否扩大本轮产品修复由主审判断。
- 证据边界：选择器和总数是浏览器事实；“不存在任何其他隐藏入口”未穷举。源码 `BrainMiningPanel.tsx` 中 `RECENT_RUN_LIMIT=8` 与 `loadRuns` 支持该判断。

## 已验证的主要行为

- BRAIN：全部 11 个新运行家族选项、5 个结论、20 个家族筛选；搜索空态与清除；4 种排序；RUN #162 的真实结果详情、PnL／滚动 Sharpe／Drawdown、2019 至 2023 年表；16 条候选的全部／入选／未入选、第二页与 5／10／20 条密度。拒绝、缺测与逻辑分不足未改成成功状态。
- Design System：八个分类、无业务处理器的按钮展示、字段／复选／滑块、富选项菜单、内层 tabs／disclosure、23 行示例表末页、六种反馈状态；四向 tooltip；dialog／drawer 的 Tab、Shift+Tab、Escape、关闭按钮与焦点恢复；通知关闭、恢复、触发。英文／浅色样例已恢复。
- Evolution：117 条方法论提案到第 24 页并返回，30 条账本到第 6 页，7 条已处理提案到第 2 页；提案 #124／#123 互斥展开，权重／校准，诊断，线上表达式编辑后取消。没有启用、拒绝、回滚或提议新因子。
- Methodology：38 个字段、52 个可调用算子（68 个登记）、15 个公式均到末页；所有分类及 T1／T2；三类无匹配搜索；字段、签名／源码、公式披露；五个数据来源。实测收盘价覆盖率 96.24% 与静态字段定义保持区别。
- Zoo：3 条原有、保存日期为 11 月 3 日的内置示例；方向／状态／五种排序、空搜索与清除焦点、详情、删除取消及 Escape、5／10 行、分析页、小样本明确说明、SHARPE／IC 提示；行内及详情内的选股交接均预选唯一因子且未运行。

## 审计事故：Zoo 回测交接自动开始计算

点击一次「回测: Earnings Yield (E/P)」后，目标页显示「计算状态：运行中 · 单任务」「回测中…」，没有点击 Run。事前核对的 `setParams` 片段被错误当作完整交接合同，漏看后续 `pendingAutoRunRef.current = true` 与执行 effect。这是审计方的安全误判，不应归因为随机网络问题。

已立即向主审报告，没有再次点击交接、运行、保存、停止或重置；返回 Zoo 并关闭任务页。该行为也会把预填参数写为上次表单配置。没有擅自尝试回滚，因为原表单快照未保留。服务端是否完成以及实际写入边界未由本分支验证，后续由主审决定。

相邻的「研报」交接在点击前已发现会自动 `generate`，因此安全阻断，没有点击。`frontend/src/app/(dashboard)/report/page.tsx:266`；回测自动触发：`frontend/src/app/(dashboard)/backtest/page.tsx:166`。这些现有交接是否改为“只载入、再显式运行”，属于产品决定；本报告不伪称已修改。

## 未验证假设与边界

- Zoo 目录表最小宽度 1240px；1440px 桌面减去导航与内边距后可能需要横向滚动。应确认操作列可达与滚动归属，而不能只检查 body overflow。证据：`ZooCatalog.tsx:163`。
- BRAIN 候选复制函数未捕获剪贴板写入失败，失败时没有用户反馈。仅为源码推断；本轮不能通过主动拒绝浏览器权限制造环境变更。证据：`BrainCandidateAudit.tsx:198`。
- 参考页面按钮样例多数没有业务处理器，这是展示用途，不应误报为生产功能失效；交互样例中的 state、弹层、菜单与分页另行检查。

## 覆盖

详细控件清单、每项实际证据与缺口见 `advanced-coverage.json`。共 92 组控件／条件状态：58 pass、2 fail、32 blocked。组内未执行的分支已逐项说明；pass 只指列出的实例，不等于该组每种数据条件都通过，更不等于 92 个按钮已穷尽。

主要缺口：Settings 全部留给主审修复版验证；BRAIN 合格项提交确认、审计表头 tooltip、行内家族徽章、全局刷新与旧兼容结果末页；Methodology 的刷新、匹配搜索、末行详情与每类反向分页；1440px 视口；Design System 的导航链接样例及静态分类最底边。没有制造失败接口、改权限或注入数据以强行补齐状态。

## 截图

目录：`/Users/a22309/.codex/visualizations/2026/07/27/019fa455-20bf-7ca3-b1c9-94534e8bb207/sidebar-audit-advanced/`。六张 JPEG 均裁掉用户侧栏与账户信息，不包含凭据。

- `brain-family-end-clipped.jpg`：长菜单键盘问题。
- `brain-result-detail.jpg`：真实结果下层证据。
- `reference-surfaces-en-light.jpg`：英文浅色浮层样例页面。
- `evolution-loaded-review.jpg`：演化列表与展开状态。
- `methodology-formula-last-page.jpg`：公式末页。
- `zoo-catalog-dark.jpg`：三条本地示例目录。

这是生产基线审计，不是主审修复版验收、部署确认或用户视觉批准。
