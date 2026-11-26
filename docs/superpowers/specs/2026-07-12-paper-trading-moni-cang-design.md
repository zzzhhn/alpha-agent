# 模拟仓（Paper-Trading）功能设计规格

> 历史规格，归档于 2026-11-26。下文保留 7 月 12 日的原始设计与当时的待确认事项，用于解释初版日线撮合的取舍，不是当前操作手册。后续方案见[模拟交易 V2 重做设计](2026-07-26-paper-trading-v2-design.md)；当前平台另有机器人账户与盘中撮合。

**版本**：v1.0  
**日期**：2026-07-12  
**适用范围**：alpha-agent 今日推荐页（/picks）模拟仓 MVP  
**状态**：待 owner 确认后再动代码

---

## 0. 背景与约束汇总

### 现有基础设施

| 资源 | 现状 |
|------|------|
| 价格数据 | `daily_prices`（ticker, date, close）：yfinance 日收盘价，只有 close，**无 open/high/low**；3y 历史，约 12MB，永久保留；这是 fill 模拟的**唯一可靠数据源** |
| 分钟数据 | `minute_bars`：rolling 2 天窗口，~100MB，`MINUTE_BARS_RETENTION_DAYS=2`；**不可用于 fill 模拟**（历史记录不存在） |
| 已有 L2 骨架 | `V026__l2_paper_trading.sql`：`l2_strategy`、`l2_order`（含 signal\_date/fill\_date/fill\_price/status）、`l2_equity_daily`；这是**系统级自动 L2 策略表**，已占用此名字空间 |
| 认证 | NextAuth，多用户（users 表），email + Google OAuth；每个 user 拥有独立 sim account |
| Neon 配额 | 512MB 免费套餐；minute\_bars 曾触发 DiskFullError；paper trading 表必须极度紧凑 |
| 前端栈 | Next.js App Router，tm-\* 设计 token，zh/en i18n，dark/light |

### 平台研究摘要

| 平台 | 初始资金 | 订单类型 | Fill 规则 | 亮点 |
|------|---------|---------|---------|------|
| Moomoo 模拟炒股 | 100 万（可重置） | Market, Limit（日内有效） | 最新成交价触碰即成交，不考虑成交量 | 盈亏展示、持仓成本 |
| 同花顺模拟炒股 | 100 万 | Market, Limit, 条件单 | 日内实时撮合 | 排行榜、社区功能（engagement driver） |
| Interactive Brokers Paper | 账户初始值 | 全部类型 | NBBO 模拟，需价差 + 1000 股深度 | 真实市场数据驱动，最接近实盘 |
| Webull Paper | 100 万美元 | Market, Limit | last price 触碰，不验证成交量 | 简单，移动端体验好 |
| TradingView Paper | 可配置 | Market, Limit, Stop | 柱线 OHLC 触碰，可选 verify-price-for-limit（cross 而非 touch） | 与图表深度集成，backtesting 一致 |

**MVP 核心借鉴**：

- Moomoo/Webull：起始 100 万，market + limit 两种订单，持仓展示（已实现/未实现 PnL）
- TradingView：日 OHLC 触碰规则（touch vs cross 可配置）——我们只有 close，用 cross 规则更诚实
- IB：诚实标签（模拟价格非实盘），equity curve 与 benchmark 对比
- **驱动留存**：持仓 PnL 可见 + equity curve 是核心；排行榜/社区是噪音，MVP 不做

---

## 1. MVP 范围

### 本次发布（V1）

- 单用户一个模拟账户（每个 users.id 对应一个 `sim_account`）
- 订单类型：市价单（Market）、限价单（Limit，DAY 有效，不支持 GTC）
- Fill 模拟：日收盘价粒度（见第 2 节算法）
- 持仓展示：每持仓未实现 PnL，总账户已实现 + 未实现 PnL
- Equity curve：账户净值随时间变化折线图，叠加 SPY 基准
- 重置：一键清空账户恢复初始资金（保留历史快照记录，不物理删除）
- 今日推荐页入口按钮：每行新增「模拟买入」按钮，点击弹出订单面板

### 推迟（V2+）

- GTC 订单（cross-day limit persistence）
- 多账户、策略账户分离
- 盘中 fill（需要 minute\_bars，受 2 天 rolling 窗口限制，不适合回望历史）
- 期权模拟
- 排行榜/社区
- 止损/止盈单
- 股息处理（V1 忽略，持仓价格直接用 adjusted close，隐式包含分红调整）

---

## 2. Fill 模拟算法

### 2.1 数据现实确认

`daily_prices` 表仅含 `(ticker, date, close)`，无 open/high/low。close 为 yfinance `auto_adjust=True` 的复权收盘价。`minute_bars` retention 为 2 天，历史不可查，不得用于 fill。

**结论**：Fill 模拟**只能基于日收盘价 close**。

### 2.2 市价单（Market Order）

- 提交时机：当日 T（用户点击时）
- Fill 时机：T+1 日 close（次一交易日收盘后 cron 批量执行）
- Fill 价格：T+1 日 `daily_prices.close`
- 理由：T 日收盘价在用户下单时已是已知量，用 T 日 close 填报是 look-ahead；用 T+1 open 需要 open 字段（不存在）；T+1 close 是最保守且数据完整的选择

### 2.3 限价单（Limit Order，DAY）

- 提交时机：T，用户指定 limit\_price
- 每日检查窗口：T+1, T+2, ..., T+N（N = 配置常量，MVP 默认 5 个交易日）
- Fill 条件（cross 规则，非 touch）：
  - 买单：`daily_prices.close(d) < limit_price`（close 严格低于限价，即 cross）
  - 卖单：`daily_prices.close(d) > limit_price`（close 严格高于限价）
- Fill 价格：**limit\_price 本身**（因为 close 已穿越，合理假设日内某时刻可以成交于 limit\_price）
- 超时：超过 N 个交易日未 fill，状态置为 `expired`
- **不支持 partial fill**（MVP 简化：全部成交或不成交）

### 2.4 边缘情况处理

| 场景 | 处理方式 |
|------|---------|
| T+1 `daily_prices` 缺失（停牌/退市） | 跳过该日继续等待；超出 N 日后 expire |
| 退市（连续 `_PRICE_FRESH_TRADING_DAYS=3` 无数据） | 强制平仓，fill 价格取最后一个已知 close，`exit_reason='delisted'` |
| 当日提交时间晚于 15:30 ET | 仍记 signal\_date=今日，T+1 开始 fill；不区分盘前盘后（数据粒度不支持） |
| gap open（开盘价远低于前日 close） | MVP 忽略：fill 价格仍为 limit\_price；已知高估情况，在诚实标签中披露 |
| 同一 ticker 重复买入 | 允许，平均成本法合并持仓（见第 6 节） |

### 2.5 诚实标签要求（MUST）

所有 fill 价格和 PnL 展示必须附带：

> 「模拟成交价基于日收盘价，非实时撮合，与实盘存在差异」  
> "Simulated fills use end-of-day close prices, not real-time execution"

---

## 3. 数据模型 DDL

### 设计原则

- 不侵入 `l2_order`/`l2_equity_daily`（这是系统 L2 策略表，命名空间隔离）
- 表名前缀：`sim_`
- 极简列集合，避免冗余 JSONB（节约磁盘）

### 3.1 `sim_account`

```sql
CREATE TABLE IF NOT EXISTS sim_account (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    initial_cash double precision NOT NULL DEFAULT 1000000.0,   -- 100万
    cash        double precision NOT NULL DEFAULT 1000000.0,    -- 可用现金
    created_at  timestamptz NOT NULL DEFAULT now(),
    reset_at    timestamptz,                                     -- 最后一次重置时间
    reset_count int NOT NULL DEFAULT 0,
    UNIQUE (user_id)   -- 每人一个账户，MVP
);
```

### 3.2 `sim_order`

```sql
CREATE TABLE IF NOT EXISTS sim_order (
    id            bigserial PRIMARY KEY,
    account_id    bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    ticker        text NOT NULL,
    side          text NOT NULL CHECK (side IN ('buy','sell')),
    order_type    text NOT NULL CHECK (order_type IN ('market','limit')),
    qty           int NOT NULL CHECK (qty > 0),
    limit_price   double precision,      -- NULL for market orders
    signal_date   date NOT NULL,         -- 下单日（T）
    fill_date     date,                  -- 成交日（T+1+）；NULL=pending/expired
    fill_price    double precision,      -- 成交价；NULL=pending/expired
    status        text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','filled','expired','cancelled')),
    expire_after_days int NOT NULL DEFAULT 5,
    created_at    timestamptz NOT NULL DEFAULT now(),
    filled_at     timestamptz
);
CREATE INDEX IF NOT EXISTS idx_sim_order_account_status
    ON sim_order (account_id, status, signal_date);
CREATE INDEX IF NOT EXISTS idx_sim_order_ticker_pending
    ON sim_order (ticker, status) WHERE status = 'pending';
```

### 3.3 `sim_position`

```sql
-- 派生自 sim_order，但物化以加速读取。
-- avg_cost = 加权平均成本，每次买入 UPSERT 重算，每次卖出减持。
CREATE TABLE IF NOT EXISTS sim_position (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    ticker      text NOT NULL,
    qty         int NOT NULL DEFAULT 0,         -- 持仓股数（0=空仓，可留行）
    avg_cost    double precision NOT NULL,      -- 加权平均买入价
    realized_pnl double precision NOT NULL DEFAULT 0.0,
    opened_at   timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (account_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_sim_position_account
    ON sim_position (account_id) WHERE qty > 0;
```

### 3.4 `sim_equity_daily`

```sql
CREATE TABLE IF NOT EXISTS sim_equity_daily (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES sim_account(id) ON DELETE CASCADE,
    as_of_date  date NOT NULL,
    portfolio_value double precision NOT NULL,  -- cash + mark-to-market positions
    cash        double precision NOT NULL,
    unrealized_pnl double precision NOT NULL,
    realized_pnl   double precision NOT NULL,
    benchmark_close double precision,           -- SPY close，用于 overlay
    UNIQUE (account_id, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_sim_equity_daily_account
    ON sim_equity_daily (account_id, as_of_date DESC);
```

### 3.5 存储占用估算（5 年，单用户）

| 表 | 行数 | 估算大小 |
|---|------|---------|
| `sim_account` | 1 | 忽略不计 |
| `sim_order` | 50 orders/day × 252 days/yr × 5 yr = 63,000 | 约 6 MB |
| `sim_position` | 最多 50 行（活跃持仓） | 忽略不计 |
| `sim_equity_daily` | 252 × 5 = 1,260 | 约 0.1 MB |
| **总计** | | **约 6.1 MB**（远低于 512MB 上限） |

即使 10 个用户同时使用，5 年总量约 61 MB，安全。

---

## 4. API 接口

### 4.1 GET /api/paper/account

返回账户概况（持仓列表 + 今日 PnL + 账户净值）。

**Response**
```json
{
  "account_id": 1,
  "cash": 870000.00,
  "portfolio_value": 1025000.00,
  "total_return_pct": 2.5,
  "unrealized_pnl": 45000.00,
  "realized_pnl": 110000.00,
  "positions": [
    {
      "ticker": "AAPL",
      "qty": 100,
      "avg_cost": 175.20,
      "current_price": 182.50,
      "unrealized_pnl": 730.00,
      "unrealized_pct": 4.17
    }
  ],
  "pending_orders": 3,
  "reset_count": 0,
  "initial_cash": 1000000.00
}
```

### 4.2 POST /api/paper/order

提交新模拟订单。

**Request**
```json
{
  "ticker": "NVDA",
  "side": "buy",
  "order_type": "limit",
  "qty": 10,
  "limit_price": 125.00
}
```

**Response（201）**
```json
{
  "order_id": 42,
  "status": "pending",
  "signal_date": "2026-07-12",
  "message": "限价单已提交，将在收盘价穿越 $125.00 时成交（最多 5 个交易日）"
}
```

**错误场景**（400）：qty <= 0，限价单缺 limit\_price，买单现金不足（按市价估算），ticker 不在 universe。

### 4.3 GET /api/paper/orders

分页查询历史订单。

**Query params**：`status`（pending/filled/expired/all），`limit`（默认 50），`offset`（默认 0）

### 4.4 DELETE /api/paper/order/{order_id}

撤销 pending 限价单（状态置 `cancelled`，不退还已扣除的冻结现金）。

### 4.5 GET /api/paper/equity-curve

返回账户历史 equity curve（供图表渲染）。

**Response**
```json
{
  "series": [
    {"date": "2026-01-02", "portfolio_value": 1000000, "benchmark_index": 100.0},
    {"date": "2026-01-03", "portfolio_value": 1008500, "benchmark_index": 100.72}
  ],
  "base_date": "2026-01-02"
}
```

`benchmark_index`：SPY 从 base\_date 归一化到 100 的指数值，与 `TmCompareEquityChart` 的 `EquityCurvePoint` 接口对齐。

### 4.6 POST /api/paper/reset

重置账户（软重置：当前持仓全部以最后已知 close 平仓，cash 恢复 initial\_cash，历史快照保留用于审计）。

**Request**：空 body 或 `{"confirm": true}`  
**Response**：`{"reset_count": 1, "cash": 1000000.00, "message": "账户已重置"}`

### 4.7 POST /api/paper/cron/fill（仅内部 cron 调用）

每日收盘后（约 21:00 ET，对应次日 09:00 北京时间）执行批量 fill：

1. 取所有 `status='pending'` 的 `sim_order`
2. 查 `daily_prices` 取当日 close
3. 按算法（第 2 节）判断是否 fill
4. 更新 `sim_order`，更新 `sim_position`（avg\_cost），更新 `sim_account.cash`
5. 写入当日 `sim_equity_daily` 快照
6. 对超时订单置 `expired`

---

## 5. UI 设计

### 5.1 今日推荐页入口按钮

**位置**：`PickRow.tsx` 中，在现有 ticker Link 右侧（或行末动作列），新增「模拟建仓」按钮。

**设计要求**：
- 样式：`text-[11px] font-tm-mono px-1.5 py-0.5 rounded border border-tm-rule text-tm-muted hover:text-tm-accent hover:border-tm-accent transition-colors`
- 中文标签：`模拟` / 英文：`Sim`
- 已有持仓时变为 `持仓中` / `Held`（`text-tm-pos`，不可重复点击则改为 `加仓` / `Add`）
- 点击后打开 `SimOrderDrawer`（右侧滑出面板，非全页跳转）

### 5.2 SimOrderDrawer（订单面板）

宽度：`w-80`（320px），从右侧 slide-in。内容分三区：

**区域 A：标的信息头**
```
NVDA                        BUY
Nvidia Corporation
当前评级：BUY  复合分：+1.42σ
最新收盘：$127.30（2026-07-11）
```

**区域 B：订单输入**
```
方向      [买入 ▼]   [卖出]
类型      [市价单]   [限价单]
数量      [___10___] 股
限价      [__125.00] ← 仅限价单显示
--
预计成本   ≈ $1,273（按收盘价估算）
可用现金   $870,000
```

**区域 C：提交 + 免责**
```
[确认提交模拟订单]
────────────────────────────────
⚠ 模拟交易。成交基于T+1日收盘价，
  非实时撮合，不代表真实交易结果。
```

### 5.3 模拟仓页面（/paper 或 /picks 内 Tab）

推荐：在 `/picks` 页内增加一个 TmSubbar Tab（「排行榜」和「模拟仓」并列），而非独立页面，降低导航层级。

**Tab 结构**（3 个子面板，SegmentedTabs 切换）：

**面板 1：账户概况**
```
账户净值          $1,025,000     +2.50%
可用现金          $870,000
未实现盈亏        +$45,000
已实现盈亏        +$110,000 ──────── [重置账户]

持仓明细（表格）
代码   数量   均价     现价    盈亏      盈亏%
AAPL    100  175.20  182.50  +730    +4.17%
NVDA     10  125.00  127.30  +230    +1.84%
```

**面板 2：Equity Curve**

复用 `TmEquityDrawdownChart`（已有组件），传入 `sim_equity_daily` 数据：
- 主线：账户净值（归一化 100）
- 叠加线：SPY（归一化 100，`text-tm-muted dashed`）
- X 轴：日期，Y 轴：指数值

**面板 3：订单记录**

表格列：日期，代码，方向，类型，数量，限价，成交价，状态，PnL

### 5.4 i18n 字符串（zh/en）

| key | 中文 | English |
|-----|------|---------|
| `sim.tab` | 模拟仓 | Paper |
| `sim.order_btn` | 模拟 | Sim |
| `sim.held_btn` | 持仓中 | Held |
| `sim.add_btn` | 加仓 | Add |
| `sim.order_type.market` | 市价单 | Market |
| `sim.order_type.limit` | 限价单 | Limit |
| `sim.order_side.buy` | 买入 | Buy |
| `sim.order_side.sell` | 卖出 | Sell |
| `sim.disclaimer` | 模拟交易，成交基于T+1日收盘价，非实时撮合 | Simulated fills use T+1 close prices, not real-time execution |
| `sim.reset_confirm` | 确认重置？持仓将以最新收盘价平仓，资金恢复100万 | Confirm reset? Positions closed at last close, cash restored to $1M |
| `sim.account.nav` | 账户净值 | Portfolio Value |
| `sim.account.cash` | 可用现金 | Available Cash |
| `sim.account.unrealized` | 未实现盈亏 | Unrealized PnL |
| `sim.account.realized` | 已实现盈亏 | Realized PnL |
| `sim.status.pending` | 待成交 | Pending |
| `sim.status.filled` | 已成交 | Filled |
| `sim.status.expired` | 已过期 | Expired |
| `sim.status.cancelled` | 已撤销 | Cancelled |

**标点规范**：所有中文输出使用全角标点（，。：（）），禁止使用任何形式破折号（改用逗号或冒号替代）。

---

## 6. PnL 正确性规则

### 6.1 平均成本法（FIFO 不做，MVP 用加权均价）

每次买入更新 `sim_position.avg_cost`：

```
new_avg_cost = (old_qty × old_avg_cost + fill_qty × fill_price)
               / (old_qty + fill_qty)
```

### 6.2 未实现 PnL

```
unrealized_pnl = (current_close - avg_cost) × qty
```

`current_close` 取 `daily_prices` 最新一条该 ticker 的 close。

### 6.3 已实现 PnL

每次卖出 fill 时：

```
realized_pnl += (fill_price - avg_cost) × sold_qty
```

卖出后 qty 减少；qty 归零时 `sim_position.qty = 0`（行保留，avg\_cost 清零重置）。

### 6.4 现金流

- 买入 fill：`cash -= fill_price × qty`（市价单预扣以最新收盘价估算；fill 后以实际 fill\_price 结算差额）
- 卖出 fill：`cash += fill_price × qty`
- 限价单提交时**不冻结现金**（MVP 简化，避免复杂度），仅在 fill 时扣款；系统不阻止理论上超额下单（单账户个人用，信任用户）

### 6.5 交易费用

MVP：**零费用**（无佣金、无印花税）。注记：加入 1 bps round-trip 费用是 V2 一行改动，已预留 `cost_bps` 字段在 `sim_order` 可选列。

### 6.6 股息

MVP 忽略。yfinance `auto_adjust=True` 的复权价格已内含分红调整，持仓价格随 adjusted close 变化，效果等同于自动再投资，但**不显式发放股息现金**。在 UI 注释中披露：「收盘价使用复权价，已隐含股息调整」。

### 6.7 账户净值计算

```
portfolio_value = cash
                + SUM(qty × last_close FOR each position WHERE qty > 0)
```

---

## 7. 诚实与风险披露清单

以下内容必须在 UI 中以可见方式展示：

1. **Fill 粒度披露**：所有成交价基于日收盘价，非实时。市价单 T+1 收盘价，限价单最早穿越收盘价。
2. **Gap Open 未处理**：限价单成交价为 limit\_price，实际盘中可能跳空导致更好或更差的成交价，模拟结果偏乐观。
3. **成交量未考虑**：不验证流动性，小盘股大单模拟不可信。
4. **无费用**：模拟不计佣金、滑点，真实收益低于模拟。
5. **无涨跌停**：美股无涨跌停，但若未来加 A 股支持需重新考虑。

### 开放问题（Owner 决策前暂定）

| 问题 | 当前预设 | 待确认 |
|------|---------|--------|
| 初始资金 | 100 万（USD，匹配 Webull/Moomoo 行业标准） | 是否换成 1,000,000 美元显示为美元，还是用抽象「积分」 |
| 限价单有效期 | DAY，最多 5 个交易日 | 是否改为 GTC（永久有效直到手动撤销） |
| 重置是否保留历史曲线 | 是（软重置，equity\_daily 打 reset\_epoch 标记） | 是否直接物理删除旧数据（简单但失去历史分析价值） |
| cron 触发时间 | 21:00 ET（盘后约 45 分钟） | 是否与现有 `daily_close` cron 合并（减少 DB 连接数） |
| 多用户 | 每用户一账户 | 未来是否允许多账户（命名策略账户）；当前 UNIQUE(user\_id) 约束需改为 UNIQUE(user\_id, account\_name) |

---

## 8. 实现顺序建议

以下仅供参考，不强制：

1. **Migration V035**：创建 `sim_account`、`sim_order`、`sim_position`、`sim_equity_daily` 四张表
2. **Backend**：`alpha_agent/api/routes/paper.py`，实现第 4 节全部端点
3. **Cron**：在 `cron_routes.py` 新增 `/paper/fill`，与 `daily_close` 同在盘后触发
4. **Frontend**：`PickRow.tsx` 加按钮，新增 `SimOrderDrawer`，新增 `/picks` 内 Tab
5. **i18n**：补全第 5.4 节 key 到 `lib/i18n.ts`
6. **测试**：fill 算法单测（mock daily\_prices，验证 market/limit/expire 三路径）；API 集成测试

---

*规格作者：Claude Code（设计辅助）。实施前须经 owner 逐条确认，特别是第 7 节开放问题。本文件不含任何可运行代码。*
