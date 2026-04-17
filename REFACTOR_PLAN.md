# AlphaCore 系统性重构方案 v1

**产出日期**：2026-04-17
**范围**：保留现有回测引擎 (`alpha_agent/backtest/engine.py`)，重设其余全部模块
**硬约束**：中文交付 (英文术语对照)、完整作品集 Portfolio Showcase、快速可演示、LLM 真正嵌入研究循环 (Option b)

---

## 0. 现状复盘 (Context)

### 0.1 Audit 发现的核心问题

| 问题 | 证据 | 影响 |
|------|------|------|
| 端点利用率 25% | 30+ backend endpoints, 仅 9 条被前端调用 | HMM Regime、Portfolio Risk、Inference、Dashboard Summary、Pipeline Latency 全部闲置 |
| LLM Switch 假功能 | `llm_control.py` 下拉切换 UI 完成, Vercel serverless 无法访问 AutoDL 的 Ollama, OPENAI_API_KEY 为空 | 切换无效且无报错; 用户点了以为生效 |
| 页面 4 充血 1 贫血 | `activity` 页仅静态文案 | Dashboard 是 "TV" 不是 "工具" |
| 信息架构错位 | 5 个 tab 按「功能模块」分，而非「研究流程」分 | 研究员入场找不到下一步 |
| 前端同步 UX | 所有操作阻塞返回完整 JSON | 回测 3-15s 白屏，无 progress |

### 0.2 研究阶段已确立的行业基线

| 判据 | 引用 | AlphaCore 的对位 |
|------|------|------------------|
| Agent 数量收敛到 2-5 | Chain-of-Alpha, Alpha-R1, AlphaAgent | 禁止复刻 TradingAgents 19-agent 堆叠 |
| 三项正则化 (AST + alignment + complexity) | AlphaAgent KDD 2025 | FactorAgent 必须实装 |
| Grammar-guided 输出 | XGrammar, Pydantic-based SOTA | 所有 LLM → JSON 触点强制 |
| 辩论轮次 ≤ 2 | FREE-MAD arXiv 2509.11035 | Critique 若存在则硬上限 2 |
| 单次交互 < 10k tokens, < 5 秒首帧 | Chain-of-Alpha, Alpha-GPT | UX 硬约束 |
| 策略生命周期作为导航轴 | TradingView, QuantConnect, WorldQuant Brain 共识 | 替换当前 5-tab 结构 |
| Vectorized fast-scan 与 event-driven 并存 | VectorBT + bt + PyBroker 共存范式 | 新增 `factor_scan` 层 |

---

## 1. 重构四大支柱 (Four Pillars)

### Pillar 1: 策略生命周期 (Strategy Lifecycle) 作为信息架构主轴

现 `activity / backtest / factors / gates / stress` 按功能分；新结构按研究员真实工作流分成 5 段，每段都有明确的「用户动词 (user verbs)」。

```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│ 1. Data  │ 2. Alpha │ 3. Signal│ 4. Back- │ 5. Report│
│  数据面板│  因子实验│   组合门 │  test 回测│   归因报告│
├──────────┼──────────┼──────────┼──────────┼──────────┤
│ universe │ hypothesis│ gate    │ run      │ equity  │
│ selector │ brainstorm│ threshold│ slider   │ tear-sheet│
│ regime   │ LLM→spec │ weight   │ walk-fwd │ LLM 归因 │
│ badge    │ smoke    │ live     │ diff     │ export  │
│ health   │ test     │ simulate │ cache    │ markdown │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

每段顶部固定三行:
- Action bar (按钮/滑杆, 当前页可执行的全部动词)
- Result canvas (图 + 表 + 数字)
- AI Inline Panel (LLM 实时解释, 可点击 follow-up)

### Pillar 2: LLM 三触点 (非 Chatbot 形态)

| 触点 | 位置 | 输入 | LLM 职责 | 输出 Schema |
|------|------|------|----------|-------------|
| T1. Hypothesis Translator | Alpha 页 | 自然语言 hypothesis | NL → FactorSpec | Pydantic `FactorSpec` (name, expression, operators, lookback, universe, justification ≤ 80w) |
| T2. Inline Explainer | Backtest/Factors/Gates 页的每张图 | 确定性代码算出的数字 | 产出 2-3 段 rationale | Markdown 段落 + 3 条 follow-up 按钮 |
| T3. Slider Live Recompute | Backtest/Gates 参数滑杆 | 参数变化事件 | 语义层重解释 (数字由代码算) | 增量文本 stream |

**关键原则**: LLM 生成 + 代码执行 + 代码判决 + LLM 解释。LLM 绝不参与数值判决 (IC/Sharpe 阈值)。

### Pillar 3: 9 层后端架构 (借鉴 Qlib + bt + PyBroker)

```
alpha_agent/
├── data/         # fetch, cache, align (AKShare/yfinance/Polygon)
├── factors/      # library + custom + AST registry + dedup
├── strategies/   # Algo composition pattern (copy from bt)
├── backtest/     # 保留现有 engine.py (event-driven)
├── scan/         # 新增: numpy+numba vectorized fast-scan, <3s
├── evaluate/     # IC/ICIR/Sharpe/MaxDD/turnover (pandas)
├── agents/       # FactorAgent, EvalAgent, Scheduler (三触点)
├── api/          # FastAPI + SSE streaming
├── storage/      # SQLite (factor registry) + Parquet (OHLCV) + DuckDB (query)
└── core/         # shared types, exceptions, config
```

### Pillar 4: 前端交互原语 (Quant Workstation Patterns)

8 条可复制的交互模式 (摘自 TradingView, QuantConnect, WorldQuant Brain):

1. Cmd+K 全局搜索 (ticker, factor, strategy, page)
2. Ticker autocomplete (带 sector 标签)
3. Multi-pane time-axis sync (拖动 equity curve, factor IC 曲线同步高亮)
4. Tear sheet (单页汇总 KPI + equity + drawdown + trades)
5. Slider live recompute (拖完 500ms debounce 后 SSE 流回首帧)
6. Inline AI Explain (每张图右上角 ✨ 按钮)
7. Backtest diff (选 2 次 run 左右对比)
8. Streaming progress (SSE: stage + percent + eta)

---

## 2. 信息架构详图 (Information Architecture)

### 2.1 导航树

```
AlphaCore
├── / (Home)
│   └── 默认预加载 NVDA 3 年 tear-sheet (demo 开场)
│
├── /data                     # Pillar 1 - Phase 1 Data
│   ├── Universe Selector     # CSI300 / SP500 / 自定义 ticker list
│   ├── Regime Badge          # HMM 输出 (当前曝光的端点 #1)
│   ├── Data Health Card      # 最后更新, 缺失日占比
│   └── Dashboard Summary     # 曝光闲置端点 #2
│
├── /alpha                    # Pillar 1 - Phase 2 Alpha
│   ├── Hypothesis Box        # NL 输入 → T1 Translator
│   ├── Factor Library Table  # IC/ICIR/turnover/corr 可排序
│   ├── IC Decay Chart        # lag 1/3/5/10/20 衰减
│   ├── Correlation Heatmap
│   ├── AST Dedup Log         # 新因子 vs 库的相似度
│   └── Inline AI Explain     # T2
│
├── /signal                   # Pillar 1 - Phase 3 Signal
│   ├── Gate Threshold Slider
│   ├── Weight Panel          # trend/momentum/entry
│   ├── Live Pass Rate        # 实时 42% 等
│   ├── Historical Pass Chart
│   └── Inference Predictions # 曝光闲置端点 #3
│
├── /backtest                 # Pillar 1 - Phase 4 Backtest
│   ├── Param Form            # 现有功能, 保留
│   ├── Walk-forward Toggle   # 新增 (PyBroker 范式)
│   ├── Equity Curve
│   ├── Drawdown
│   ├── Trade Table
│   ├── Diff Mode             # 新增: 选 2 run 左右对比
│   ├── Streaming Progress    # SSE 替代白屏
│   └── Portfolio Risk Panel  # 曝光闲置端点 #4
│
└── /report                   # Pillar 1 - Phase 5 Report
    ├── Tear Sheet            # 单页 KPI+图+trade 全套
    ├── LLM Attribution       # T2 全文归因
    ├── Pipeline Latency      # 曝光闲置端点 #5
    ├── Export Markdown       # 作品集友好
    └── Share Link (optional)
```

### 2.2 Action Verbs 清单 (每页至少 3 个按钮/滑杆)

| 页面 | User Verbs |
|------|-----------|
| /data | 切换 universe、查看 regime 详情、刷新数据 |
| /alpha | 输入假设、保存因子、删除因子、比较因子、运行 smoke test |
| /signal | 调门槛、调权重、模拟历史通过率、应用到回测 |
| /backtest | 跑回测、切换 walk-forward、对比 run、导出 equity |
| /report | 生成 tear-sheet、导出 Markdown、复制 permalink |

对照原则: `feedback_tool_not_tv.md` — 零 verb 的页面算未完成。

---

## 3. LLM 三触点详细实装

### 3.1 T1: HypothesisTranslator

**接口**: `POST /api/v1/alpha/translate`

**输入**:
```json
{
  "text": "最近换手率低 + ROE 上升的中盘股",
  "universe": "CSI500",
  "budget_tokens": 4000
}
```

**Pydantic Schema** (grammar constraint):
```python
from pydantic import BaseModel, Field
from typing import Literal

ALLOWED_OPS = Literal[
    "ts_mean","ts_rank","ts_corr","ts_std","ts_zscore",
    "rank","scale","log","sign","winsorize",
    "div","sub","mul","add","pow"
]

class FactorSpec(BaseModel):
    name: str = Field(max_length=40)
    hypothesis: str = Field(max_length=200)
    expression: str  # 后续 AST parse 验证
    operators_used: list[ALLOWED_OPS]
    lookback: int = Field(ge=5, le=252)
    universe: Literal["CSI300","CSI500","SP500","custom"]
    justification: str = Field(max_length=400)
```

**验证闭环** (参考 AlphaAgent + FactorEngine):
1. Pydantic validate 失败 → 返回 LLM 重生成
2. AST parse + operator whitelist 检查
3. 10-day smoke test (单股小样本, < 1s)
4. 若通过, 落盘 `storage/factor_registry.db` 打 `candidate` 状态
5. 真实 3 年回测由 Pillar 3 的 `scan/` 或 `backtest/` 层异步承担

**成本预算**: 单次 ≤ 3000 tokens (Claude Haiku 4.5, ¥0.008/次)

### 3.2 T2: Inline Explainer

**接口**: `POST /api/v1/explain` (SSE)

**输入**:
```json
{
  "context": "backtest_result",
  "payload": {
    "ic": 0.037, "icir": 0.48, "sharpe": 1.2, "max_dd": -0.18,
    "monthly": [...], "worst_month": "2024-03", "best_month": "2024-07"
  }
}
```

**输出**: SSE 流式文本 + 3 条 structured follow-ups

**Regex Red-flag 拦截**: 输出后置过滤，命中下列词则重 prompt
- "我算了" / "经过计算" / "显著性"
- 任何浮点数字 (禁止 LLM 复述/重算)

### 3.3 T3: Slider Live Recompute

**机制**: 前端 debounce 500ms → POST → SSE 回首帧 (图 + KPI) < 1s, 完整 rationale < 4s

**关键工程点**:
- Backend 用 Pillar 3 的 `scan/` 层 (numpy+numba) 做数值；LLM 只做语义增量
- 前端维护 "last stable result" 状态, 新请求 in-flight 期间显示旧结果 + loading shimmer

### 3.4 LLM Provider 修复 (解决 "切 Gemma 4 无效" 问题)

| 环境 | 原设计 | 新设计 |
|------|--------|--------|
| Vercel serverless | Ollama @ AutoDL (网络不通) + OPENAI_API_KEY 空 | DeepSeek API + Claude Haiku 作为 fallback |
| AutoDL 自托管 | Ollama gemma3-27b | 保留, 用于 batch 离线任务 |

**实装点**:
1. 删除 `llm_control.py` 的运行时切换 UI (是 anti-pattern)
2. 改为环境变量 `LLM_PROVIDER=deepseek|claude|ollama` 启动时固定
3. Vercel 环境默认 `deepseek`, AutoDL 环境默认 `ollama`
4. 前端仅显示 "Powered by DeepSeek" 这类静态 badge

---

## 4. Vectorized Fast-Scan 引擎 (新增 scan/ 层)

### 4.1 为什么要加

现有 `backtest/engine.py` 是 event-driven, 单次 3-15s。滑杆拖动场景需 < 1s 首帧。两套引擎并存:

| 场景 | 引擎 | 目标延迟 | 精度 |
|------|------|----------|------|
| 滑杆调参数、因子扫描 | `scan/` (numpy+numba) | < 800ms | 近似 (忽略交易成本/滑点) |
| 最终回测、tear-sheet | `backtest/engine.py` | 3-15s | 完整 (含 10bp/5bp 成本 + VWAP 滑点) |

### 4.2 实装要点 (抄自 VectorBT)

```python
# alpha_agent/scan/vectorized.py
import numpy as np
from numba import njit

@njit(cache=True)
def rolling_zscore(arr: np.ndarray, window: int) -> np.ndarray:
    # 预编译, 首次 300ms, 后续 <10ms
    ...

@njit(cache=True)
def cross_sectional_rank(mat: np.ndarray) -> np.ndarray:
    ...
```

Pre-computed warm cache 在服务启动时加载常用 universe 的 OHLCV 到内存 (Parquet → numpy)。

---

## 5. 闲置端点曝光矩阵 (25% → 90% 利用率)

| 闲置端点 | 目标页面 | 曝光形式 |
|----------|----------|----------|
| `/api/v1/market_state` (HMM Regime) | /data | Regime Badge (top-right) + Tooltip 详情 |
| `/api/v1/dashboard/summary` | /data | Dashboard Summary Card |
| `/api/v1/inference/predict` | /signal | Inference Predictions 面板 |
| `/api/v1/portfolio/stress` (现 stress 页) | /backtest | Portfolio Risk Panel (并入 backtest 详情页) |
| `/api/v1/audit` | /report | Pipeline Latency + Audit Log |
| `/api/v1/decision/evaluate` | /signal | Live Decision 流 |
| `/api/v1/alpha/factors` | /alpha | Factor Library Table |
| `/api/v1/gate/simulate` | /signal | 已在用, 升级为实时流 |
| `/api/v1/orders` | /report | Trade Table (backtest 内嵌) |

---

## 6. 30 秒 Demo 脚本 (面试场景)

```
T+0s   打开 alpha-agent-delta.vercel.app
       → / 页默认预加载 NVDA 3 年 tear-sheet, 直接有内容
T+3s   点 /alpha 页, Hypothesis Box 输入 "低换手 + ROE 上升"
       → T1 Translator 5 秒内 stream 出 FactorSpec JSON
T+10s  点 "Smoke Test" 按钮
       → 10 天 IC 图 1 秒内出现
T+13s  点 /backtest, 拖动 RSI period 滑杆 14 → 20
       → SSE 首帧 < 1s, equity 曲线变化 + T2 inline rationale stream
T+20s  点 "Compare Run" 选前一次 run diff
       → 左右对照 equity + KPI delta
T+25s  点 /report → tear-sheet + "Export Markdown" 生成作品集友好文件
T+30s  结束
```

**Aha 点**:
- < 1s 首帧响应 (scan/ + SSE)
- 可点击 follow-up (越用越懂)
- 导出 Markdown (作品集硬需求)

---

## 7. 五周路线图 (Weekly Deliverable)

| Week | 主轴 | Backend Deliverable | Frontend Deliverable | Exit Criteria |
|------|------|--------------------|--------------------|---------------|
| W1 | 架构迁移 + LLM 修复 | 9 层目录搭建; `llm_control.py` 删除; `LLM_PROVIDER` 环境变量; DeepSeek + Claude Haiku provider class | 导航重写为 `/data /alpha /signal /backtest /report`; 空页占位 | `curl /openapi.json` 列路由, LLM provider 启动即验证可达 |
| W2 | T1 HypothesisTranslator + scan/ 层雏形 | `POST /alpha/translate` + Pydantic + AST parse + smoke test; `scan/vectorized.py` 雏形 (rolling zscore + rank) | /alpha 页 Hypothesis Box + FactorSpec JSON 展示 | 一句自然语言 → 可执行 FactorSpec 入库 |
| W3 | T2 Inline Explainer + SSE | `POST /explain` SSE 流 + red-flag regex 拦截 | 每张图右上角 ✨ Explain 按钮, stream 渲染 Markdown | backtest 结果页点 ✨ 出现流式归因 |
| W4 | T3 Slider Live Recompute + 闲置端点曝光 | scan/ 层 + 前端 debounce 500ms SSE; Dashboard Summary/Regime Badge/Inference/Pipeline Latency 接入 | Backtest 页滑杆实时重算; /data 页 Regime Badge; /signal 页 Inference 面板 | 滑杆拖动 < 1s 首帧; 端点利用率 ≥ 85% |
| W5 | Diff + Tear-sheet + Export + Demo 雕琢 | Backtest diff endpoint + tear-sheet 聚合 + Markdown export endpoint | Backtest diff 模式; /report 页 tear-sheet + Export Markdown; 首页 NVDA 预加载 | 30 秒 demo 脚本全程 pass |

可选 W6 (若时间充裕): 引入 QuantaAlpha 风格 trajectory mutation (加分项, 非 MVP)。

---

## 8. 验收 Checklist (四层验收, 参考 `feedback_four_layer_acceptance.md`)

### 8.1 配置层
- [ ] `pyproject.toml [project.dependencies]` 含所有 router 顶层 import 的依赖
- [ ] `LLM_PROVIDER` 在 Vercel / AutoDL 两环境都有值
- [ ] `OPENAI_API_KEY` (若用 DeepSeek OpenAI-compat) 非空
- [ ] tsc --noEmit 过

### 8.2 应用层
- [ ] `/openapi.json` 列出 ≥ 25 条路由
- [ ] 每条闲置端点有至少 1 个前端组件消费
- [ ] `/healthz/routers` 返回每个 router 的 loaded/error 状态
- [ ] Pydantic schema 对 FactorSpec 全覆盖
- [ ] red-flag regex 拦截单元测试通过

### 8.3 中间件层
- [ ] SSE `Content-Type: text/event-stream` + `X-Accel-Buffering: no`
- [ ] CORS 允许 SSE 的 EventSource
- [ ] Next.js middleware 不缓存 `/api/v1/explain`

### 8.4 Infra 层
- [ ] Vercel deploy 后 `curl /api/health` 返回 200 + JSON
- [ ] 首页硬刷 (Cmd+Shift+R) 后 30 秒 demo 脚本全程 pass
- [ ] 浏览器 Network 面板 SSE 流首帧 < 1s
- [ ] `/api/v1/alpha/translate` P95 < 5s

---

## 9. 红线 (禁止事项)

1. 任何数值计算交给 LLM (IC/Sharpe/VaR/相关矩阵)
2. Persona prompt ("你是格雷厄姆")
3. 辩论轮次 > 2
4. 单次交互 > 10k tokens
5. 运行时切 LLM provider 的 UI (启动时固定)
6. 白屏阻塞式回测 (必须 SSE)
7. 零 verb 的 "仅展示" 页面
8. try/except 吞 ImportError 到 stderr (必须 surface 到 `/healthz/routers`)
9. 复刻 TradingAgents 19-agent 架构
10. Chatbot 形态 (浮动 bubble)

---

## 10. 关键引用 (可追溯性)

- AlphaAgent (KDD 2025): AST 原创性 + 三项正则
- RD-Agent(Q) (NeurIPS 2025 Microsoft): Thompson sampling 调度
- Chain-of-Alpha (arXiv 2508.06312): dual-chain 简洁架构
- Alpha-R1 (arXiv 2512.23515): 8B RL reasoning
- FactorEngine (arXiv 2603.16365): 三分离 (逻辑/参数/计算)
- QuantaAlpha (arXiv 2602.07085): trajectory 进化 (可选 W6)
- VectorBT: numpy+numba 向量化范式
- PyBroker: walk-forward 第一公民
- bt: Algo/AlgoStack 组合模式
- Qlib: DataHandler + Processor 学习管线
- XGrammar EBNF-Guided Generation: 语法约束生产级方案
- FREE-MAD (arXiv 2509.11035): 辩论轮次 ≤ 2 实证
- FAITH (arXiv 2508.05201): LLM 数值不可靠实证

---

**下一步**: 待用户批准方案后, 进入 W1 落地。
