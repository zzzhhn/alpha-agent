# Alpha Agent：基于大语言模型的量化因子研究系统

[English](README.md) | **中文**

> 多智能体系统，输入自然语言研究方向，自动生成并回测 A 股（沪深300）量化 Alpha 因子。

## 架构

```
用户输入："寻找沪深300短期反转因子"
  │
  ▼
┌──────────────────────┐  假设列表   ┌──────────────────────┐
│   HypothesisAgent    │────────────▶│     FactorAgent      │
│    （假设生成）       │             │    （因子表达式生成） │
└──────────────────────┘             └──────────┬───────────┘
         ▲                                       │ 因子表达式
         │ 反馈（REFINE）                         ▼
┌────────┴─────────────┐  回测指标   ┌──────────────────────┐
│      EvalAgent       │◀────────────│   BacktestAgent      │
│  （接受/拒绝/优化）  │             │  （IC、ICIR、夏普率） │
└──────────────────────┘             └──────────────────────┘
         │ ACCEPT
         ▼
  FactorRegistry（SQLite，AST 结构去重）
```

不可变的 `PipelineState` 在各 Agent 间流转。反馈循环最多执行 3 轮，
之后进行接受、拒绝或终止。

## 核心特性

- **递归下降解析器** — 完整支持中缀算术（`+`、`-`、`*`、`/`、`**`）、
  比较运算符和函数调用，运算符优先级符合数学惯例
- **多智能体反馈循环** — EvalAgent 驱动迭代优化；被接受的因子写入
  SQLite，基于 AST 结构哈希自动去重
- **IC / ICIR 回测** — Rank IC、多空组合夏普率、换手率、最大回撤，
  以及 1/2/3/5/10/20 日前瞻的 Alpha 衰减曲线
- **远程 GPU 部署 Gemma 4 26B** — Ollama 运行在 AutoDL RTX5090 上；
  本地通过 SSH 隧道调用，本地磁盘零占用
- **LLMClientFactory** — 修改 `.env` 中的一行配置即可在 Ollama 和任意
  OpenAI 兼容 API 之间切换，无需改动代码

## 技术栈

| 组件 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.12 | 模式匹配、asyncio 改进 |
| LLM 运行时 | Ollama（远程） | 不用 LangChain；50 行 HTTP 客户端，完全透明可解释 |
| 数据 | AKShare + Parquet 缓存 | 免费无需 API Key；24 小时缓存，3 年数据约 50 MB |
| 配置 | pydantic-settings + `.env` | 类型安全；密钥不进源码 |
| 因子存储 | SQLite | 轻量级注册表，树哈希去重 |
| 回测 | 自研 pandas 引擎 | 无需 C 扩展；约 300 行，每一行都能在面试中解释清楚 |
| 界面（M4） | Streamlit | 零前端代码；交互式 Pipeline 仪表盘 |

## 快速上手

**前置要求：** Python 3.12+、`uv` 或 `pip`、可访问的 GPU 服务器（运行 Ollama），
或 OpenAI 兼容 API Key 作为备选。

```bash
# 1. 克隆并安装
git clone <repo-url> alpha-agent
cd alpha-agent
pip install -e ".[dev]"

# 2. 配置
cp .env.example .env
# 编辑 .env，填写 LLM_PROVIDER 及对应的 URL 或 API Key

# 3.（Ollama）开启 SSH 隧道到远程 GPU 服务器
ssh -N -L 11434:localhost:6006 -p <端口> root@<服务器地址>

# 4. 运行
alpha-agent "寻找短期反转因子"
```

### 备选方案：OpenAI 兼容 API

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

无需修改任何代码——`LLMClientFactory` 在启动时读取 `LLM_PROVIDER`。

## 因子表达式 DSL

解析器支持兼容 Qlib 的函数调用语法，同时支持完整的中缀算术。

**语法规则（运算符优先级由低到高）：**

```
expr    := compare
compare := add_sub ((">" | "<" | ">=" | "<=") add_sub)?
add_sub := term    (("+"|"-") term)*
term    := unary   (("*"|"/") unary)*
unary   := "-" unary | power
power   := atom    ("**" atom)?
atom    := 数字 | "$"标识符 | 标识符"("参数列表")" | "("expr")"
```

**示例：**

```
Rank(-Delta($close, 5))                        # 5 日短期反转因子
Corr($close, $volume, 20)                      # 20 日量价相关性
($close - Mean($close, 20)) / Std($close, 20)  # 20 日 Z-score（中缀写法）
Rank($close / Ref($close, 5) - 1)              # 5 日动量因子
```

**可用算子：**

| 类型 | 算子 |
|------|------|
| 时序算子 | `Ref`、`Mean`、`Sum`、`Std`、`Var`、`Max`、`Min`、`Delta`、`EMA`、`WMA`、`Corr`、`Cov`、`Skew`、`Kurt`、`Med`、`Slope`、`Count` |
| 截面算子 | `Rank`、`Zscore` |
| 逐元素算子 | `Abs`、`Sign`、`Log`、`If` |
| 特征字段 | `$open`、`$close`、`$high`、`$low`、`$volume`、`$amount` |

## 项目结构

```
alpha-agent/
├── alpha_agent/
│   ├── agents/               # HypothesisAgent、FactorAgent、BacktestAgent、EvalAgent
│   ├── factor_engine/        # parser.py、evaluator.py、ast_nodes.py、regularizer.py
│   ├── data/                 # AKShareProvider、ParquetCache、CSI300Universe
│   ├── backtest/             # BacktestEngine、MetricsCalculator
│   ├── pipeline/             # orchestrator.py、state.py、registry.py
│   ├── llm/                  # OllamaClient、OpenAIClient、LLMClientFactory
│   ├── report/               # HTMLReportGenerator（M4）
│   └── ui/                   # Streamlit 应用（M4）
├── tests/                    # 90+ 测试用例，覆盖所有模块
├── .env.example
├── pyproject.toml
└── status.json
```

## 开发指南

```bash
# 运行所有测试
pytest

# 查看覆盖率报告
pytest --cov=alpha_agent --cov-report=term-missing

# 跳过需要外部网络的慢速测试
pytest -m "not slow"

# 代码检查
ruff check .
```

当前测试规模：**90+ 个测试用例**，涵盖解析器（41 个）、求值器（34 个）、
回测引擎（18 个）以及 Agent/Pipeline 模拟测试。

## 开发路线图

| 里程碑 | 描述 | 状态 |
|--------|------|------|
| M1 | 因子引擎（解析器、求值器、回测引擎） | 已完成 |
| M2 | LLM 集成（Ollama、Gemma 4 26B、HypothesisAgent、FactorAgent） | 已完成 |
| M3 | 多智能体循环（BacktestAgent、EvalAgent、FactorRegistry） | 进行中 |
| M4 | Streamlit 界面 + HTML 报告生成 | 计划中 |
| M5 | 完善、80% 测试覆盖率、CLI、错误处理加固 | 计划中 |

## License

MIT
