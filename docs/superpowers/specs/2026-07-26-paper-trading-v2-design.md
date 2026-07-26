# 模拟交易 V2 重做设计（2026-07-26）

三路 agent team（市场调研 6 家券商、UI 十原则审计、产品差距分析）合成，用户已拍板。
V1 spec：2026-07-12-paper-trading-moni-cang-design.md（成交引擎语义不变，本次不动）。

## 用户三点不满 → 根因

1. 「UI 低级、与平台风格不符」→ 组件语言自成一派：圆角卡片、实心填充分段控件、
   手写按钮样式、window.confirm（全仓唯一原生弹窗）。tm- token 本身没用错。
2. 「功能与真实模拟盘相距甚远」→ 真缺口是四个：下单零风控校验（可卖不存在的持仓）、
   交易与推荐零归因关联、诚实标签只闪现一次、无逐票盈亏归因。「像券商」的大部分
   功能（盘中/partial fill/期权/排行榜）在日频约束下属于该砍的噪音。
3. 「一头雾水」→ 无 onboarding。

## 已拍板的决策

| 决策 | 结论 |
|---|---|
| 信息架构 | 一次到位：独立路由页 /paper（4 个 URL 可寻址 tab），Sidebar DECISIONS 组加入口 |
| 快捷入口 | PickRow 的 SimOrderDrawer 保留，双入口并存，视觉同步新规范 |
| 止损单 | 这轮不做，降 P2（日频降级版有「以为有保护其实没有」体感风险） |
| 归因埋点 | 仅自动：picks 抽屉下单自动带 pick 关联；/paper 手动单归因字段可空 |
| 现金校验口径 | 下单时按最新收盘估算、不加 buffer；成交时硬性复核，不足则成交失败并给可读原因 |

## P0 范围

### 后端（文件：alpha_agent/api/routes/paper.py、alpha_agent/paper/fill_engine.py、新迁移）
1. 下单校验：买入现金充足（最新 daily_prices.close × qty ≤ cash）、卖出持仓充足
   （qty ≤ sim_position.qty），不满足 400 + 可读中英文错误。
2. 成交复核：fill 时现金不足 → 订单标记 failed 并记录原因（新枚举值或 detail 字段）。
3. V038 迁移：sim_order 加可空 pick_date DATE + pick_ticker TEXT（归因），幂等 ADD
   COLUMN IF NOT EXISTS。⚠️ Neon 8-01 才恢复，V038 的应用时序已并入 #495 runbook
   第 0 步（apply_migrations 先于一切）；paper 端点当前对 prod 本来就整体不可用，
   无 V037 式部署时序风险。
4. 归因聚合端点：GET /api/paper/attribution，按 ticker 聚合已实现/未实现盈亏、
   跟单笔数 vs 自主笔数。OpenAPI 快照必须重生成。

### 前端结构（/paper 路由页）
- app/(main)/paper/page.tsx：TmScreen/TmPane 承载，tab= overview | trade | curve |
  orders，落 URL query。Sidebar DECISIONS 组加「模拟仓 PAPER」。
- BasketEdgeStrip 入口按钮改 Link href="/paper"。PaperTradingModal 退役删除。
- SimOrderDrawer 保留，下单时自动携带该行 pick 的 date+ticker 归因。
- orders tab 内加「按标的汇总」归因表（吃 /api/paper/attribution）。

### 视觉平价修复（迁移中一并落地，全部对齐 BrainMiningPanel 基准）
1. KPI 去卡片壳 → Metric 式裸露布局（label 9px uppercase tracking，值 tabular-nums）
2. 全部按钮换 TmButton（primary/secondary/ghost，无圆角）
3. window.confirm → 内嵌两步确认（照 BrainMiningPanel SubmitControl 模式）
4. 分段控件去实心填充 → border+text 变色（GradeBadge 语言）；实心只留唯一主 CTA
5. input 去圆角；关闭按钮统一 lucide X；订单状态徽标改平台统一 chip 几何
   （border-only、9px、px-1 py-px）
6. 诚实标签常驻：账户概况、订单、下单区三处固定展示「模拟成交基于收盘价，非实时
   撮合」（i18n key sim.disclaimer 已有）

### Onboarding（driver.js，约 5KB，零依赖）
6 步：定位一句话 → T+1 成交规则 → 第一单入口（高亮 picks 行「模拟」按钮）→
三个面板怎么看 → 诚实标签强调 → CTA 收尾。首次进入 /paper 或首次开抽屉触发，
可跳过，页面常驻「?」重看入口。localStorage 记录已看。

## P2（明确不做）
盘中/实时模拟、partial fill、期权、多账户、排行榜/社交、GTC、止损单（连同其
日频降级版）、初始资金可配置。理由见三份调研报告与 V1 spec。

## § 十原则 re-check 表

| 原则 | 本次落点 |
|---|---|
| 1 意图对齐 | PickRow 抽屉保留（列表内就地跟单）；/paper 承担完整管理 |
| 2 认知负担 | 四视图拆分，overview 不再同屏堆 KPI+持仓+下单+免责 |
| 3 状态可见 | 保留现有 loading/成功反馈；成交失败新增可读原因展示 |
| 4 Forgiveness | window.confirm → 两步确认（SubmitControl 模式）；重置有阻尼 |
| 5 Affordance | 分段控件/徽标/关闭按钮统一平台既有视觉语言 |
| 6 设计消失 | 组件语言全面对齐 BrainMiningPanel，不再「跳出」 |
| 7 免说明书 | onboarding 6 步 + 空状态引导 + 常驻「?」 |
| 8 尊重时间 | 保留 Promise.all 并发加载；driver.js 5KB 不拖累 |
| 9 不撒谎 | 诚实标签三处常驻；市价单不编造预估成本；止损单因体感风险砍掉 |
| 10 单一主操作 | 每个 tab 一个 primary action（trade=提交；orders=撤单；curve 纯展示） |

## § Cross-cutting conventions audit

| 项 | 约定 |
|---|---|
| i18n | 全部新文案走 t(locale, key)，zh/en 双语，中文全角标点、禁破折号 |
| 字体 | font-tm-mono 等宽体系，数值 tabular-nums |
| layout | TmScreen/TmPane 包裹，同 /brain /backtest |
| Sidebar | DECISIONS 组新增 /paper 项（lucide Wallet 图标） |
| 数据 locale | 金额 Intl.NumberFormat en-US，日期 ISO |
| 图标 | lucide-react（strokeWidth 约 1.75），禁 emoji |

## 实施切分（subagent，文件集互斥可并行）
- Task A 后端：校验 + V038 + 归因端点 + OpenAPI 重生成 + 测试
- Task B 前端：/paper 路由 + 组件迁移 + 视觉平价修复 + 归因表 + 抽屉埋点
- Task C onboarding：driver.js 接入 + 6 步 tour + 空状态 +「?」入口（依赖 B 落地后）
验收：tsc/ruff/pytest/OpenAPI 门禁全绿 + 用户硬刷新视觉验收（浏览器扩展不可用时用户为视觉门禁）。
