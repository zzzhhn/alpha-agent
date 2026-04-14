# AlphaCore UI Overhaul Proposal

> 审阅文档, 请用户决策后再实施

## 一, 现状诊断

### 边栏导航 (11 项)

| # | 名称 | 路径 | 交互性 | 内容价值 | 建议 |
|---|------|------|--------|---------|------|
| 1 | Backtest | /backtest | 完全交互 | 核心 | KEEP |
| 2 | Factors | /factors | 完全交互 | 核心 | KEEP + 吸收 Alpha |
| 3 | Gates | /gates | 完全交互 | 核心 | KEEP + 吸收 Gateway |
| 4 | Stress | /stress | 完全交互 | 核心 | KEEP + 吸收 Portfolio |
| 5 | Inference | /inference | 零 (只读轮询) | 有价值 | MERGE 入 Backtest |
| 6 | Market | /market | 极少 (ticker切换) | 有价值 | MERGE 入 Factors |
| 7 | Alpha | /alpha | 零 (只读轮询) | 与 Factors 重叠 | DELETE |
| 8 | Portfolio | /portfolio | 零 (只读轮询) | 与 Stress 重叠 | MERGE 入 Stress |
| 9 | Orders | /orders | 零 (只读轮询) | 低 (无真实订单) | DELETE |
| 10 | Gateway | /gateway | 零 (只读轮询) | 与 Gates 重叠 | MERGE 入 Gates |
| 11 | Audit | /audit | 极少 (筛选) | 有价值 | MERGE 入新 Activity Log |
| - | System | /system | 零 (隐藏页) | 低 | DELETE |

### Phase 2 & 3 UI 问题

- **Factors 页**: 表格和热力图用纯 div 堆砌, 无视觉层次, z-score badge 颜色单调
- **Gates 页**: 滑块和进度条缺乏设计感, pass/fail 卡片无差异化
- **Stress 页**: 场景选择卡片像 radio button 列表, 瀑布图用 div 宽度模拟, 不够专业

---

## 二, 合并策略

### 最终边栏结构 (4 个核心页面 + 1 个辅助页面)

```
Research
  📉 Backtest      ← 吸收 Inference 的 Agent Voting 和 Decision Output
  🧬 Factors       ← 吸收 Market 的 heatmap 和指标卡片, Alpha 的 Factor Library
  🚦 Gates         ← 吸收 Gateway 的实时 gate 状态
  🌪️ Stress        ← 吸收 Portfolio 的持仓表和风险指标

System
  📋 Activity Log  ← 合并 Audit 的决策时间线 + Orders 的执行记录 (只读, 可折叠)
```

### 各页面合并细节

#### 1. Backtest (吸收 Inference)

现有: 左侧表单 + 右侧结果

新增区域:
- 结果区底部增加 **"AI Decision Panel"** 折叠面板
  - 来自 Inference: Agent Voting (Macro/Momentum/Sentiment/Quant 四个 agent 的评分和权重)
  - 来自 Inference: Decision Output (方向, 置信度, regime)
  - 触发条件: 回测完成后自动展示 (基于回测的 ticker 和最新数据)
- 参考 ai-hedge-fund: 每个 agent 显示 reasoning trace (纯文本解释为什么给出该信号)

#### 2. Factors (吸收 Market + Alpha)

现有: ticker 搜索 + feature stats 表格 + correlation heatmap + factor registry

新增区域:
- 页面顶部增加 **"Market Context"** 条带
  - 来自 Market: 5个 KPI 卡片 (RSI, MACD, Bollinger %B, Volatility, Log Return)
  - 随 ticker 搜索联动刷新
- Feature Stats 表格下方增加 **"Factor Library"** 标签页
  - 来自 Alpha: 已保存 factor 的 expression, IC, ICIR, Sharpe, status
  - 来自 Alpha: Factor Editor placeholder 删除 (无实际功能)

#### 3. Gates (吸收 Gateway)

现有: ticker 搜索 + threshold/weight 滑块 + 评分卡片

新增区域:
- 评分卡片下方增加 **"Live Gate Status"** 折叠面板
  - 来自 Gateway: 实时 gate 评估表 (rule name, pass/fail, confidence, reason)
  - 来自 Gateway: Rule Configuration 状态 (enabled/disabled)
  - 标注 "Simulation vs Live" 区分用户模拟结果和实际系统状态

#### 4. Stress (吸收 Portfolio)

现有: 场景选择 + 持仓列表 + KPI + 瀑布图

新增区域:
- 页面顶部增加 **"Current Portfolio"** 面板
  - 来自 Portfolio: Positions 表格 (ticker, direction, weight, qty, avg price, current price, PnL)
  - 来自 Portfolio: Risk Metrics 卡片 (Sharpe, Max Drawdown, Beta, VaR)
  - 一键 "Import to Stress Test" 按钮: 将当前持仓自动填入压力测试的 positions 列表

#### 5. Activity Log (合并 Audit + Orders)

- 时间线视图, 两个标签页:
  - **Decisions**: 来自 Audit 的决策时间线 (可展开推理链)
  - **Executions**: 来自 Orders 的订单历史 (执行状态, 滑点)
- 这是唯一的纯只读页面, 仅作审计和追溯用途

### 删除的页面

| 页面 | 删除原因 |
|------|---------|
| /alpha | 内容 100% 被 /factors 覆盖 |
| /orders | 无真实订单系统, 内容移入 Activity Log |
| /inference | 核心内容移入 Backtest 的 AI Decision Panel |
| /market | 核心内容移入 Factors 的 Market Context |
| /portfolio | 核心内容移入 Stress 的 Current Portfolio |
| /gateway | 核心内容移入 Gates 的 Live Gate Status |
| /system | 隐藏页, 无导航入口, 无用户价值 |

---

## 三, UI 设计方案

### 设计系统选择: Linear + Sentry 混合

**理由**: Linear 提供最专业的 dark-mode 数据密集型界面系统 (luminance-stepped surfaces, semi-transparent borders), Sentry 补充 frosted glass 和 tactile button 质感. 两者都是 dark-mode-native, 适合量化研究工具的专业感.

### 全局 Design Tokens

```css
/* Surface hierarchy (Linear) */
--surface-0: #08090a;     /* 最深背景 (sidebar) */
--surface-1: #0f1011;     /* 面板背景 */
--surface-2: #191a1b;     /* 卡片背景 */
--surface-3: #28282c;     /* hover 态 */

/* Text hierarchy (Linear) */
--text-primary: #f7f8f8;
--text-secondary: #d0d6e0;
--text-tertiary: #8a8f98;
--text-muted: #62666d;

/* Borders (Linear) */
--border-subtle: rgba(255,255,255,0.05);
--border-standard: rgba(255,255,255,0.08);
--border-solid: #23252a;

/* Accent (brand) */
--accent-primary: #5e6ad2;    /* Linear indigo — 主按钮, active 态 */
--accent-hover: #828fff;

/* Semantic (ClickHouse + Sentry) */
--positive: #27a644;           /* 盈利, pass */
--negative: #ef4444;           /* 亏损, fail */
--warning: #f59e0b;            /* 中性, 注意 */
--highlight: #c2ef4e;          /* Sentry lime — 重点数据高亮 */

/* Component */
--card-bg: rgba(255,255,255,0.02);
--card-border: rgba(255,255,255,0.08);
--card-radius: 8px;
--button-radius: 6px;

/* Typography */
--font-primary: 'Inter Variable', 'SF Pro Display', system-ui, sans-serif;
--font-mono: 'Berkeley Mono', 'SF Mono', 'Menlo', monospace;
```

### Factors 页 UI 重设计

```
┌─────────────────────────────────────────────────────┐
│  🧬 Factor Analytics          [NVDA ▾] [Analyze]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─── Market Context (折叠条带) ──────────────────┐ │
│  │ RSI: 62.4  MACD: +0.8  BB%: 0.71  σ: 0.023   │ │
│  │ (5个 KPI pill, surface-2 背景, 单行横排)        │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Feature Stats ──────────────────────────────┐ │
│  │ ┌────────┬────────┬────────┬────────┬───────┐  │ │
│  │ │ Name   │ Value  │ Mean   │ Std    │ Z     │  │ │
│  │ ├────────┼────────┼────────┼────────┼───────┤  │ │
│  │ │ RSI_14 │  62.4  │  50.2  │  15.3  │ +0.80 │  │ │
│  │ │ MACD   │  +0.8  │  -0.1  │   1.2  │ +0.75 │  │ │
│  │ │ ...    │        │        │        │       │  │ │
│  │ └────────┴────────┴────────┴────────┴───────┘  │ │
│  │  Z-score 用色带: <-2 深红 | -1~1 中性 | >2 深绿 │ │
│  │  整行背景色根据 z-score 渐变 (opacity 0.05~0.15)│ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Correlation Matrix ─────┐ ┌── Factor Lib ──┐ │
│  │  (热力图, 7x7 grid)        │ │ (已保存因子表) │ │
│  │  cell 颜色:                │ │ IC, ICIR,      │ │
│  │  正相关: indigo 渐变       │ │ Sharpe, status │ │
│  │  负相关: coral 渐变        │ │ badge          │ │
│  │  对角线: lime highlight    │ │                │ │
│  └────────────────────────────┘ └────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**关键设计决策**:
- Feature Stats 表格: 行背景根据 z-score 有微妙的红/绿渐变 (opacity 0.05~0.15), 不是纯色 badge
- Correlation Matrix: 用 indigo→white→coral 色谱, 不是默认的红绿 (避免色盲问题, 且与品牌色一致)
- Market Context: 折叠态只显示一行 pill 状 KPI, 点击展开显示 sparkline 趋势
- Factor Library: 与 Feature Stats 并列而非堆叠, 利用水平空间

### Gates 页 UI 重设计

```
┌─────────────────────────────────────────────────────┐
│  🚦 Gate Editor              [NVDA ▾] [Simulate]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─── Control Panel (frosted glass) ──────────────┐ │
│  │                                                 │ │
│  │  Threshold  ═══════●═══  0.50                   │ │
│  │                                                 │ │
│  │  Weights:                                       │ │
│  │  Trend      ═══════════●  0.40                  │ │
│  │  Momentum   ════════●═══  0.35                  │ │
│  │  Entry      ═════●══════  0.25                  │ │
│  │                                                 │ │
│  │  滑块轨道: surface-3 背景, 填充色 accent-primary│ │
│  │  滑块手柄: 12px 圆形, border 2px solid white    │ │
│  │  frosted glass: blur(12px) saturate(150%)       │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Composite Score ────────────────────────────┐ │
│  │                                                 │ │
│  │  ██████████████████████░░░░░░░  0.72 / 0.50    │ │
│  │  ▲ threshold marker                             │ │
│  │                                                 │ │
│  │  进度条: 渐变填充 (negative→warning→positive)    │ │
│  │  threshold 位置用竖线标记 + 虚线                  │ │
│  │  数值用 font-mono 48px 显示                      │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌── Trend ───────┐ ┌── Momentum ──┐ ┌── Entry ──┐ │
│  │ Score: 0.82    │ │ Score: 0.65  │ │ Score: 0.54│ │
│  │ ██████████░░░  │ │ ████████░░░░ │ │ ███████░░░ │ │
│  │ ✓ PASSED       │ │ ✓ PASSED     │ │ ✓ PASSED   │ │
│  │                │ │              │ │            │ │
│  │ 卡片边框:      │ │ 左边框 3px:  │ │ pass=green │ │
│  │ pass=positive  │ │ fail=negative│ │ fail=red   │ │
│  └────────────────┘ └──────────────┘ └────────────┘ │
│                                                     │
│  ┌─── Live Gate Status (折叠) ────────────────────┐ │
│  │  来自 /gateway 的实时数据                       │ │
│  │  "System Status" 标签 + 灰色 badge              │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**关键设计决策**:
- Control Panel: 使用 Sentry 的 frosted glass 效果, 半透明背景悬浮在页面上方
- Composite Score: 大号 mono 字体显示分数, 进度条用三色渐变 (red→yellow→green)
- Gate Cards: 左边框 3px 色带表示 pass/fail, 不用全背景色 (太刺眼)
- 滑块: 自定义样式, thumb 为白色圆形, track 填充用 accent-primary

### Stress 页 UI 重设计

```
┌─────────────────────────────────────────────────────┐
│  🌪️ Stress Test                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─── Current Portfolio (折叠面板) ───────────────┐ │
│  │  来自 /portfolio 的实时持仓                     │ │
│  │  NVDA 45% | AAPL 25% | MSFT 20% | ...         │ │
│  │  Sharpe: 1.2  MaxDD: -8.3%  VaR: -2.1%        │ │
│  │  [Import to Stress Test →]                      │ │
│  └────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Scenario Selection ─────────────────────────┐ │
│  │                                                 │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────┐│ │
│  │  │ 🦠       │ │ 📈       │ │ 💥       │ │ 💻 ││ │
│  │  │ COVID-19 │ │ 2022     │ │ GFC 2008 │ │Dot ││ │
│  │  │ Crash    │ │ Rate     │ │ Financial│ │Com ││ │
│  │  │          │ │ Hike     │ │ Crisis   │ │    ││ │
│  │  │ SPY -34% │ │ SPY -25% │ │ SPY -57% │ │-49%││ │
│  │  └──────────┘ └──────────┘ └──────────┘ └────┘│ │
│  │                                                 │ │
│  │  卡片: surface-2 背景, 选中态 accent-primary    │ │
│  │  边框 + 微光效果 (box-shadow inset)             │ │
│  │  SPY 跌幅用 negative 色 mono 字体               │ │
│  └─────────────────────────────────────────────────┘ │
│                                                     │
│  ┌─── Positions ──────┐ ┌─── Results ─────────────┐ │
│  │ Ticker    Value    │ │                         │ │
│  │ [NVDA ▾] [$100K ]│ │ Portfolio Return        │ │
│  │ [AAPL ▾] [$50K  ]│ │ -42.8%                  │ │
│  │ [+ Add Position]  │ │ (font-mono, 48px,       │ │
│  │                    │ │  negative 色)           │ │
│  │ 输入框: surface-2  │ │                         │ │
│  │ 底部边框式 (IBM    │ │ P&L: -$64,200           │ │
│  │ Carbon 风格)       │ │ Remaining: $85,800      │ │
│  │                    │ │                         │ │
│  │ [▶ Run Stress Test]│ │ ┌── Waterfall ────────┐ │ │
│  │                    │ │ │ NVDA  ████████ -$52K │ │ │
│  │                    │ │ │ AAPL  ███░░░░ -$12K  │ │ │
│  │                    │ │ │                      │ │ │
│  │                    │ │ │ 横向条形图:           │ │ │
│  │                    │ │ │ 负值向左 (negative)  │ │ │
│  │                    │ │ │ 正值向右 (positive)  │ │ │
│  │                    │ │ │ 排序: 贡献度从大到小 │ │ │
│  │                    │ │ └──────────────────────┘ │ │
│  └────────────────────┘ └─────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**关键设计决策**:
- Scenario Cards: 卡片式选择器替代 radio button, 每张卡片有 emoji + 名称 + SPY 跌幅预览
- 选中态: accent-primary 边框 + 内部微光 (box-shadow: inset 0 0 20px rgba(94,106,210,0.15))
- Current Portfolio: 折叠面板, 展开后显示实时持仓, "Import" 按钮一键导入
- Waterfall: 真正的横向条形图 (不是 div width 模拟), 负值红色向左, 正值绿色向右
- 大数字: Portfolio Return 用 48px mono 字体, 颜色随正负变化
- Position 输入: IBM Carbon 风格底部边框输入框 (不是全边框), 更干净

---

## 四, 实施优先级

| 优先级 | 任务 | 工作量 | 影响 |
|--------|------|--------|------|
| P0 | 全局 design tokens (CSS variables) | 小 | 全局基础 |
| P0 | 删除 7 个旧页面, 精简 sidebar 到 5 项 | 中 | 立即清爽 |
| P1 | Stress 页 UI 重写 (场景卡片 + waterfall + portfolio 导入) | 大 | 视觉冲击最大 |
| P1 | Gates 页 UI 重写 (frosted glass + 大数字 + 色带卡片) | 中 | 交互感提升 |
| P1 | Factors 页 UI 重写 (z-score 渐变行 + 双色热力图 + market context) | 大 | 数据密度提升 |
| P2 | Backtest 页增加 AI Decision Panel | 中 | 叙事深度 |
| P2 | Activity Log 新页面 (Audit + Orders 合并) | 中 | 完整性 |
| P3 | 动效: 滑块拖拽实时预览, 卡片选中过渡, 数字滚动 | 小 | 精致度 |

---

## 五, 待决策项

请审阅以上方案后确认:

1. **边栏结构**: 是否同意 11→5 的合并方案? Activity Log 是否需要保留?
2. **设计系统**: Linear + Sentry 混合方案是否满意? 是否偏好其他模板 (ClickHouse 的 neon 风格, IBM Carbon 的工程风格)?
3. **合并优先级**: 是先做 UI 美化 (P1) 还是先做内容合并 (P0)?
4. **Factors 页的 Market Context**: 折叠条带 vs 固定显示?
5. **Stress 页的 Current Portfolio**: 默认折叠 vs 默认展开?
6. **配色偏好**: accent 色用 Linear indigo (#5e6ad2) 还是其他?
