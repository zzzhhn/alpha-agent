# Alpha-Agent v4 · Phase 1 设计文档

| 字段 | 值 |
|------|----|
| 状态 | Draft (pending user review) |
| 起草日期 | 2026-05-10 |
| 起草人 | Bobby + Claude（brainstorming） |
| 范围 | Phase 1：单用户、本地优先、混合流式架构的散户股票决策卡片 |
| 后续阶段 | Phase 2：watchlist + 实时告警；Phase 3：LLM 简报增强；Phase 4：多用户 + 鉴权 |

## 1. 背景与目标

### 1.1 用户与场景

用户画像：大学生、量化小白、股票散户，手动交易（非算法），资金有限、时间有限、统计训练有限，偏好免费数据源。

JTBD（Job to be Done）：
> 「帮我决定本周该买什么、为什么、入场止损目标各在哪里。要有理有据可追溯，不只是回测里 alpha-t 显著的因子。」

用户痛点：
1. **不可信**：因子回测结论与个股「现在是否该买」之间隔着一道鸿沟
2. **不可解**：评级背后的信号、权重、数据时间不透明
3. **不可执行**：评级 OW 不等于今天 192 块就能买，需要入场区间 / 止损 / 仓位

### 1.2 设计目标

| 目标 | 度量 |
|------|------|
| 高认知制高点 | 用户看完一张卡片即可做出"买/不买/等"决策，无需自己拼信息 |
| 透明可追溯 | 每个数字标注来源 + 时间戳；评级算法公式可在卡内展开 |
| 多信号融合 | 10 路独立信号，权重可调，单点失败不拖死全局 |
| 免费优先 | yfinance / SEC EDGAR / FRED / agent-reach；BYOK LLM 由用户付费 |
| 决策即行动 | 入场 / 止损 / 目标 / R:R / 建议仓位 在卡片左栏始终可见 |

### 1.3 非目标（Phase 1 排除）

- 自动下单 / broker 集成
- 多用户 / SSO / RBAC
- 移动端原生 app（响应式 web 即可）
- 加密货币 / 港股 / A 股（仅 SP500 美股）
- 长线深度基本面建模（DCF / LBO 由 BYOK Rich 模式 LLM 完成，不放后端）
- 推送渠道完整实现（Phase 1 仅占位 UI + DB log）

### 1.4 关键约束

- Vercel 部署（Functions + Cron）
- Neon Postgres（free tier，serverless 自动 sleep/wake）
- Next.js 16 App Router 前端
- FastAPI 后端（复用 alpha-agent v3 现有代码）
- 单用户、localStorage 存 watchlist / 设置 / BYOK key
- 总月成本 ≤ Vercel + Neon free tier；BYOK 由用户付

## 2. 高层架构

### 2.1 数据流总图

```
            ┌─ Slow Daily Cron · 21:30 北京 ────────┐
            │  factor / analyst / earnings /         │
            │  insider / macro                        │
            ├─ Fast Intraday Cron · 每 15min ────────┤
            │  technicals / options / news /          │
            │  premarket                               │
            ├─ Alert Dispatcher · 每 5min ────────────┤
            │  drain alert_queue                       │
            └────────┬────────────────────────────────┘
                     │ writes
                     ▼
            ┌────────────────────────────────────────┐
            │ Neon Postgres                            │
            │ ├─ daily_signals_slow                    │
            │ ├─ daily_signals_fast                    │
            │ ├─ alert_queue                           │
            │ ├─ error_log / cron_runs                 │
            │ └─ ratings_cache (composite + breakdown) │
            └────────┬────────────────────────────────┘
                     │ reads
                     ▼
            ┌────────────────────────────────────────┐
            │ FastAPI 业务端点                         │
            │ ├─ /api/picks/lean                       │
            │ ├─ /api/stock/{ticker}                   │
            │ ├─ /api/brief/{ticker}  (BYOK)           │
            │ ├─ /api/_health, /api/_health/signals    │
            │ └─ /api/_health/cron                     │
            └────────┬────────────────────────────────┘
                     │ HTTP
                     ▼
            ┌────────────────────────────────────────┐
            │ Next.js 前端                              │
            │ ├─ /picks         lean 列表 + 可展开      │
            │ ├─ /stock/[t]     完整决策卡片             │
            │ ├─ /alerts        告警 landing             │
            │ └─ /settings      BYOK / 权重 / 推送渠道    │
            └────────────────────────────────────────┘
```

### 2.2 关键架构决策

| # | 决策 | 替代方案 | 选择理由 |
|---|------|---------|---------|
| 1 | 混合流式（slow+fast cron 双频）| 纯每日 batch / 纯实时 | 散户日内决策需 15min 颗粒；slow cron 跑慢档信号节省资源 |
| 2 | Postgres 三表 + 一队列 | 内存缓存 / Redis | 持久化 + 跨 cron 共享 + 免费层够用 |
| 3 | BYOK LLM | 服务端付费 | 成本归零，用户决定 provider 与额度 |
| 4 | localStorage watchlist | 服务端账户 | 单用户阶段无需鉴权，部署成本最低 |
| 5 | 复用 v3 factor_engine | 重写 | 现有 panel + AST + smoke 测试沉淀已可用 |

## 3. 组件设计

### 3.1 数据层（10 路 signal 模块 · 9 进 composite + 1 仅展示）

目录：`alpha_agent/signals/`

统一契约：

```python
# alpha_agent/signals/base.py
class SignalScore(TypedDict):
    ticker: str
    z: float            # clip 到 [-3, +3] 的标准分
    raw: float | dict   # 原始值（卡片透明化展示）
    confidence: float   # 数据完整度 [0, 1]
    as_of: datetime
    source: str         # "yfinance" / "edgar" / "fred" / "agent-reach"
    error: Optional[str]  # 失败时的错误描述

def fetch_signal(ticker: str, as_of: datetime) -> SignalScore: ...
```

10 个模块：

| 模块 | 数据源 | 频次 | 默认权重 |
|------|--------|------|----------|
| `factor.py` | 复用 v3 panel | 慢 | 0.30 |
| `technicals.py` | yfinance OHLCV | 快 | 0.20 |
| `analyst.py` | yfinance recommendation | 慢 | 0.10 |
| `earnings.py` | yfinance earningsDate + EPS | 慢 | 0.10 |
| `news.py` | agent-reach | 快 | 0.10 |
| `insider.py` | SEC EDGAR Form 4 | 慢 | 0.05 |
| `options.py` | yfinance options chain | 快 | 0.05 |
| `premarket.py` | yfinance preMarketPrice | 快 | 0.05 |
| `macro.py` | FRED (DGS10/2/DXY/VIX) | 慢 | 0.05 |
| `calendar.py` | FRED + agent-reach | 慢 | 0.00（仅展示，不计 composite）|

> **Composite 加总约束**：上表前 9 个模块权重之和恒等于 1.00。calendar 是第 10 个模块，但其 SignalScore 不进入 fusion，只在卡片"催化剂"区展示经济事件邻近度。后文凡说"10 路 signal"指模块数；"9 路 fusion 信号"指进 composite 的子集。

### 3.2 信号融合引擎

目录：`alpha_agent/fusion/`

```
fusion/
├── normalize.py    # 截面 z-score + winsorize ±3σ
├── weights.py      # 默认权重 + 用户 override
├── combine.py      # 加权求和（confidence=0 信号自动剔除并重归一化）
├── rating.py       # 5-tier 映射 + confidence
└── attribution.py  # 反向归因
```

输出 schema（`RatingCard`，前后端共享 type）：

```typescript
{
  ticker: string;
  rating: "BUY" | "OW" | "HOLD" | "UW" | "SELL";
  confidence: number;          // [0, 1] = 1 / (1 + variance_of_z)
  composite_score: number;     // z-space
  as_of: string;               // ISO 8601 with TZ
  breakdown: Array<{
    signal: string;
    z: number;
    weight: number;
    contribution: number;      // z * weight
    raw: any;
    source: string;
    timestamp: string;
    error?: string;
  }>;
  top_drivers: string[];
  top_drags: string[];
}
```

5-tier 阈值：

| Tier | composite_score |
|------|-----------------|
| BUY | > 1.5σ |
| OW | 0.5 ~ 1.5σ |
| HOLD | -0.5 ~ 0.5σ |
| UW | -1.5 ~ -0.5σ |
| SELL | < -1.5σ |

### 3.3 股票卡片视图

页面：`frontend/src/app/(dashboard)/stock/[ticker]/page.tsx`

布局：**双栏 · 左固定决策栏 + 右滚动**（Section 4.1 选项 B）。

左栏（240-280px，sticky）7 区块：

```
1 · Identity              ticker · 公司名 · 行业
2 · Price snapshot        当前价 · 1d/5d/30d 涨跌
3 · Rating badge          [OW] · composite +1.23σ · confidence 0.72
4 · Action box (核心)     入场 / 止损 / 目标 / R:R / 建议仓位
5 · Quick actions         [+ Watchlist] [生成 LLM 简报] [设价格提醒]
6 · Tier 标签             复用 v3 verdict (Pure Alpha · Long Short · SN)
7 · 数据时间戳            Slow / Fast / 状态指示
```

右栏（70%，垂直滚动）6 个 section：

```
1 · Thesis           Bull 3 / Bear 3（Lean: 规则模板 · Rich: LLM）
2 · Attribution      小雷达 + 可排序明细表（Section 4.2 选项 C）
3 · Price / Tech     TradingView lightweight chart + 指标
4 · Fundamentals     P/E vs 行业中位、P/B、ROE、3y 营收
5 · Catalysts        财报日 + 分析师 target 分布 + 新闻 + insider
6 · Sources          每 section 的数据源 + 时间戳总表
```

Action box 算法（关键，必须在 footer "📐 计算说明" 暴露）：

| 字段 | 公式 |
|------|------|
| 入场区间 | 当前价 ± ATR(14) × 0.5 |
| 止损 | 当前价 − ATR(14) × 1.5 |
| 目标 | `min(analyst.targetMeanPrice, max(close[180d]) × 1.05)` |
| R:R | (target − entry_mid) / (entry_mid − stop) |
| 建议仓位 | `user.max_single_pos × confidence` |

R:R < 1.5 时 Action box 灰显并 banner 警告"风险回报比不足"。

### 3.4 Lean vs Rich 模式

| 维度 | Lean（默认） | Rich（用户主动） |
|------|-------------|-----------------|
| LLM 调用 | 0 | 1 次 BYOK |
| Thesis | 规则模板从 top_drivers/top_drags 拼装 | LLM 1-2 页 markdown |
| 渲染时间 | < 500ms | 5-15s 流式 |
| 成本 | $0 | 用户 BYOK |
| 缓存 | Postgres 永久 | Postgres 24h（per ticker per date）|

API key 永不存后端 DB，仅 request body 短暂出现。

## 4. 数据流时序

### 4.1 写链路

**Slow Daily Cron**（21:30 北京 = 09:30 ET 盘前）：
- Universe = SP500 ~500 ticker
- 慢档 5 信号 + partial fuse → `daily_signals_slow`
- 预计 8-12min（asyncio.gather batch_size=20）
- Vercel Function timeout 上调到 300s

**Fast Intraday Cron**（每 15min · 9:30-16:00 ET 工作日）：
- Universe = watchlist ∪ top_100_from_slow
- 快档 4 信号 + 拉 slow 同 ticker → full fuse
- 写 `daily_signals_fast` + 检测 alert 写 `alert_queue`
- 预计 60-90s

**Alert Dispatcher**（每 5min）：
- `SELECT * FROM alert_queue WHERE dispatched=false`
- 推送到用户配置的 channel（Phase 1 占位：写 console + DB log）

### 4.2 读链路

| 端点 | 用途 | 目标 SLA |
|------|------|---------|
| `GET /api/picks/lean` | 列表页 | < 500ms p95 |
| `GET /api/stock/{ticker}` | 卡片 lean 模式 | < 800ms p95 |
| `POST /api/brief/{ticker}` | Rich 模式 LLM | 5-15s（流式）|

### 4.3 时序约束

1. 慢档先于快档：fast cron 9:30 ET 第一次跑时若 slow 未结束，先用快档 4 信号生成"临时评级"，标 `partial=true`
2. Alert 去重：同 ticker 同 type 在同一"30 分钟桶"内只触发一次（应用层用 `floor(epoch/1800)` 计算 bucket，写 DB 时拼入 unique index）
3. 盘外不跑 fast：非交易时段直接 return，省 Vercel 配额
4. Macro 信号缓存 24h，500 ticker 共享同一份 snapshot

## 5. 错误处理与降级

### 5.1 Per-signal 隔离

`safe_fetch()` 包装层捕获 `(ConnectionError, TimeoutError, HTTPError, KeyError, ValueError)`，**禁止裸 `except Exception`**。失败信号返回 `confidence=0` + `error` 字段。fusion 阶段权重重新归一化。卡片 attribution 行变灰显示错误描述。

### 5.2 Cron 失败矩阵

| 失败模式 | 检测 | 用户可见 | 兜底 |
|---------|------|---------|------|
| Slow 整体超时 | 跑批 > 12min | banner: "数据延迟" | 用前一日 row |
| Fast 单 batch 失败 | 写 `error_field` | 该 ticker stale 标志 | 用 daily_signals_slow |
| Cron 函数 crash | Vercel logs ERR | `_health/cron` 反映 | 下次窗口重试 |
| 连续 3 次失败 | counter | 顶 banner 红色 | 邮件/Telegram 告警占位 |

Cron handler 永远 `return 200 + {ok: false, errors: [...]}`，不抛 5xx。

### 5.3 Neon DB 不可用

3 次 exponential backoff 重试，仍失败返回 503：

```json
{
  "code": "DB_UNAVAILABLE",
  "retry_after_sec": 5,
  "message": "Database is waking up, please retry in a few seconds.",
  "as_of": "2026-05-10T15:46:23Z"
}
```

前端 5s 自动 retry，不显示错误页。

### 5.4 LLM (BYOK) 失败

| 类型 | HTTP | 用户提示 | 降级 |
|------|------|---------|------|
| Auth 401/403 | "API key 无效" | 弹 Settings |
| Rate limit 429 | "限流，{retry_after}s 后重试" | 倒计时按钮 |
| Network/Timeout | "Provider 暂不可达" | "改用规则模板"按钮 |
| Content policy 400 | "请求被拒" | 自动改用规则模板 |

Lean 永远在那里作为最后保险。

### 5.5 部分数据场景

| 场景 | 处理 |
|------|------|
| 新 IPO < 60d | factor confidence=0.3 + banner |
| 退市 | slow cron 标 `delisted=true`，从 universe 排除 |
| 停牌 / 涨跌停 | rating 保留 + Action box 灰显 |
| 财报当日 | banner: "建议盘后再决策"，Action 锁定 |
| 字段缺失 | 单字段 "—"，section 标 "数据不全" |

### 5.6 Frontend 三级降级

```
一级 · stale 数据 + banner   (as_of 距现在 > 4h 盘中 / 24h 盘外)
二级 · section 级 placeholder (单 section 字段全 null)
三级 · page-level error boundary (API 5xx 持续 / 网络断)
```

### 5.7 错误观测端点（CLAUDE.md 三板斧）

| 端点 | 用途 |
|------|------|
| `GET /api/_health` | tunnel + db + last cron 状态 |
| `GET /api/_health/signals` | 10 信号 last_success / last_error / 24h count |
| `GET /api/_health/cron` | 三 cron 最近 5 次跑批 |

独立于业务路径，避免业务 bug 污染观测。

### 5.8 错误日志

```sql
CREATE TABLE error_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT now(),
  layer TEXT,             -- 'signal' / 'fusion' / 'api' / 'cron'
  component TEXT,
  ticker TEXT,
  err_type TEXT,
  err_message TEXT,
  context JSONB
);
```

每周扫一次 TOP10 frequent → 改进信号 robustness。

## 6. 测试策略

### 6.1 测试金字塔与覆盖目标

```
E2E Playwright       ~8 paths · 5min
Integration tests    ~30 cases · 1min
Unit (pure)          ~150 cases · <10s
```

| 模块 | Coverage |
|------|----------|
| `signals/*` | ≥ 90% |
| `fusion/*` | ≥ 95% |
| `storage/*` | ≥ 80% |
| `api/*` | ≥ 80% |
| frontend components | ≥ 70% |
| **整体** | **≥ 80%** |

### 6.2 Fixture 化外部响应

`tests/fixtures/{yfinance,edgar,fred,agent_reach}/` 存 frozen 响应。**禁止任何测试直连真实 API**（除 nightly smoke）。刷新命令：`make refresh-fixtures TICKER=AAPL DATE=...`。

### 6.3 关键 Unit Test 清单

每信号 4-5 个测试（happy / missing / new_ipo / range / timeout），共 ~45。

Fusion ~30 个（boundary tier、normalize 边界、redistribute、attribution 顺序、sector 多样性）。

Storage ~15 个（idempotent INSERT、alert dedup、JOIN、Neon wake retry）。

### 6.4 集成测试（Neon 分支）

CI 每次 run 创建 ephemeral Neon branch：

```bash
neonctl branches create --name "ci-$RUN_ID"
# run integration tests
neonctl branches delete --id $BRANCH_ID  # always
```

### 6.5 API Contract

`openapi-typescript /api/openapi.json > frontend/src/lib/api-types.gen.ts`，CI 强制 `git diff --exit-code` 检测 schema drift。

### 6.6 E2E (Playwright) 8 critical paths

```
1. /picks 加载 → 看到 ≥1 张评级卡
2. 进 /stock/[t] → 8 section 全渲染 < 800ms
3. R:R < 1.5 → 警告 banner
4. 无 BYOK 点 LLM 简报 → 弹 Settings
5. 配 BYOK 触发 Rich → 流式 markdown 渲染
6. /stock/INVALID → 404 fallback
7. seed 24h 旧数据 → stale banner
8. 切 dark/light + zh/en → 无 regression
```

### 6.7 Nightly Smoke（真 API）

每天 03:00 北京跑 ~10 个真实数据源测试，失败发邮件不阻塞 PR。

### 6.8 部署后验收（CLAUDE.md 三板斧）

deploy.sh 末尾：

```bash
curl -fI "$BACKEND_URL/api/_health" | grep "Content-Type: application/json"
ROUTES=$(curl -s "$BACKEND_URL/openapi.json" | jq '.paths | keys | length')
[ "$ROUTES" -ge "$EXPECTED_ROUTES" ]
curl -s "$FRONTEND_URL/_next/static/chunks/main-*.js" | grep -q "$BACKEND_URL"
curl -fs "$BACKEND_URL/api/picks/lean?limit=1" | jq -e '.picks | length > 0'
```

任一失败 → exit 1。

### 6.9 长尾 case 回归

`tests/edge_cases/test_known_edge_cases.py` 维护已发现的长尾：IPO < 60d、退市、停牌、财报日、含点 ticker（BRK.B）、ETF 无基本面等。每发现新 bug 必须先加一条再 fix。

### 6.10 CI 工作流

```
Pre-commit:   ruff + mypy + tsc + next lint
PR:           unit + integration (Neon) + contract + E2E (preview) + coverage gate
Post-merge:   deploy + 三板斧 + smoke
Nightly:      Real API smoke (10 cases)
```

## 7. Schema 定义

### 7.1 Postgres tables

```sql
-- 慢档（每日一次）
CREATE TABLE daily_signals_slow (
  ticker TEXT NOT NULL,
  date DATE NOT NULL,
  composite_partial DOUBLE PRECISION,
  breakdown JSONB,
  fetched_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (ticker, date)
);

-- 快档（每 15min 覆盖最新行）
CREATE TABLE daily_signals_fast (
  ticker TEXT NOT NULL,
  date DATE NOT NULL,
  composite DOUBLE PRECISION,
  rating TEXT,
  confidence DOUBLE PRECISION,
  breakdown JSONB,
  partial BOOLEAN DEFAULT false,
  fetched_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (ticker, date)
);

CREATE TABLE alert_queue (
  id BIGSERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  type TEXT NOT NULL,             -- 'rating_change' / 'gap_3sigma' / 'iv_spike' / 'news_velocity'
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  dedup_bucket BIGINT NOT NULL,   -- = floor(EXTRACT(EPOCH FROM created_at) / 1800), 应用层填入
  dispatched BOOLEAN DEFAULT false,
  UNIQUE (ticker, type, dedup_bucket)
);
CREATE INDEX idx_alert_queue_pending ON alert_queue (dispatched, created_at) WHERE dispatched = false;

CREATE TABLE cron_runs (
  id BIGSERIAL PRIMARY KEY,
  cron_name TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  ok BOOLEAN,
  error_count INT,
  details JSONB
);

CREATE TABLE error_log (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ DEFAULT now(),
  layer TEXT,
  component TEXT,
  ticker TEXT,
  err_type TEXT,
  err_message TEXT,
  context JSONB
);
```

### 7.2 API 端点契约

```
GET /api/picks/lean?limit=20&scope=watchlist|sp500
  → { picks: RatingCard[], as_of, stale: bool }

GET /api/stock/{ticker}
  → { card: FullStockCard, sources: SourceManifest }

POST /api/brief/{ticker}
  Body: { llm_provider, api_key, depth: 'short'|'long' }
  → text/event-stream (markdown chunks)

GET /api/_health
  → { tunnel, db, last_slow_cron, last_fast_cron, last_dispatcher }

GET /api/_health/signals
  → { signals: [{ name, last_success, last_error, error_count_24h }] }

GET /api/_health/cron
  → { slow: CronRun[], fast: CronRun[], dispatcher: CronRun[] }
```

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| yfinance API 改动 / 限流 | 中 | 高 | nightly smoke + fixture 化测试，发现 break 早 |
| Neon free tier suspend 增加用户感知延迟 | 高 | 中 | 5s 自动 retry + 友好 loader UI |
| Vercel Function 300s 仍跑不完 SP500 slow | 低 | 高 | asyncio batch + 必要时拆 universe 分两个 cron |
| BYOK LLM provider 内容拒绝率高 | 中 | 中 | Lean 永远兜底；prompt 设计避免争议 |
| agent-reach 新闻搜索质量差 | 中 | 低 | news 信号权重仅 0.10；可降级到禁用 |
| EDGAR 限流（10 req/sec） | 中 | 中 | per-fetcher RLock + jitter；缓存 24h |
| Vercel cron schedule 漂移 | 低 | 低 | cron_runs 表追踪实际跑批时间，监控漂移 |

## 9. Phase 1 交付边界

**包含**：
- 10 信号实现 + fixture 测试
- Fusion engine + 5-tier rating + attribution
- 三 cron + Postgres schema
- /picks 列表页 + /stock/[ticker] 完整卡片
- Lean 模式（规则模板 thesis）
- Settings 页 BYOK 配置
- 三个 health 端点
- E2E 8 paths + 80% coverage

**不包含（Phase 2 backlog）**：
- Rich 模式 LLM 简报实际接通（仅占位 UI + endpoint stub）
- /alerts 页与推送实际触达（仅 DB log）
- watchlist UI 高级管理（仅 add/remove）
- 信号权重可视化编辑器（仅 JSON）
- 跨设备同步（仅 localStorage）

**完全不做（Phase 3+ 或永不）**：
- 多用户 / 鉴权
- 自动下单
- A 股 / 港股
- 移动端原生

## 10. 推荐执行顺序

```
Day 1-3:   Schema + storage 层 + Neon 分支 CI 流水线
Day 4-7:   10 signal 模块 + fixture 测试 (并行 by signal)
Day 8-10:  Fusion engine + rating + attribution + unit test
Day 11-12: 三 cron handler + integration test
Day 13-15: 三个 API 端点 + health 端点 + contract 测试
Day 16-18: Frontend /stock/[ticker] 双栏布局 + Action 栏 + Attribution
Day 19-21: Frontend /picks 列表页 + Settings 页 + Lean Thesis 模板
Day 22-23: E2E + 部署 + 三板斧验收
Day 24:    端到端 acid test + 文档
```

预估 24 个工作日，单人 full-time。

## 11. 端到端 Acid Test（Phase 1 通关条件）

1. 浏览器进 `/picks` → 看到 20 张评级卡片（mix BUY/OW/HOLD/UW/SELL）
2. 点击某 ticker → 进 `/stock/[ticker]` → 8 section 全渲染 < 800ms
3. 左栏 Action 显示具体入场区间 / 止损 / 目标 / R:R / 仓位
4. Attribution 雷达 + 表格双联动，点列头排序工作
5. Footer "📐 计算说明"展开能看到 ATR(14) 公式 + 数据时间戳
6. 点 "生成 LLM 简报"无 BYOK → 弹 Settings 引导
7. Settings 配 BYOK key → 重试 → 流式 markdown 渲染（mock provider 即可）
8. 关掉电脑 8h 再开 → /picks 仍能 serve（用前一日 row + stale banner）
9. `curl /api/_health/signals | jq` 显示 10 行，全 last_success_at 在合理范围
10. CI 跑 `pytest --cov` 显示整体 coverage ≥ 80%

任一项卡死 = Phase 1 未达成。

---

**Status**：Draft，等用户 review。下一步 `/superpowers:writing-plans` 制定实施计划。
