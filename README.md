# Alpha Agent: LLM-Powered Quantitative Factor Research

**English** | [中文](README_zh.md)

> A multi-agent system that takes natural language research directions and produces
> backtested quantitative alpha factors for A-share (CSI300) markets.

## Architecture

```
User: "find short-term reversal factors for CSI300"
  │
  ▼
┌──────────────────────┐  hypotheses   ┌──────────────────────┐
│   HypothesisAgent    │──────────────▶│     FactorAgent      │
│  (idea generation)   │               │  (expr generation)   │
└──────────────────────┘               └──────────┬───────────┘
         ▲                                         │ factor expressions
         │ feedback (REFINE)                       ▼
┌────────┴─────────────┐  metrics      ┌──────────────────────┐
│      EvalAgent       │◀──────────────│   BacktestAgent      │
│  (accept/reject/     │               │  (IC, ICIR, Sharpe)  │
│      refine)         │               └──────────────────────┘
└──────────────────────┘
         │ ACCEPT
         ▼
  FactorRegistry (SQLite, AST dedup)
```

Immutable `PipelineState` flows through each agent. The feedback loop runs up to
3 iterations before accepting, rejecting, or escalating.

## Key Features

- **Recursive descent parser** — full infix arithmetic (`+`, `-`, `*`, `/`, `**`),
  comparison operators, and function calls with correct operator precedence
- **Multi-agent feedback loop** — EvalAgent drives iterative refinement; accepted
  factors persist to SQLite with structural AST dedup
- **IC / ICIR backtesting** — rank IC, long-short Sharpe, turnover, max drawdown,
  and alpha decay across forward lags 1/2/3/5/10/20 days
- **Gemma 4 26B on remote GPU** — Ollama on AutoDL RTX5090; local machine uses
  an SSH tunnel with zero disk footprint
- **LLMClientFactory** — single `.env` toggle switches between Ollama and any
  OpenAI-compatible API; no code changes required

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12 | Pattern matching, `asyncio` improvements |
| LLM runtime | Ollama (remote) | No LangChain; 50-line HTTP client, fully transparent |
| Data | AKShare + Parquet cache | Free, no API key; 24-hour cache, ~50 MB for 3yr data |
| Config | pydantic-settings + `.env` | Type-safe; secrets never in source |
| Factor storage | SQLite | Lightweight registry with tree-hash dedup |
| Backtest | Custom pandas engine | No C extensions; ~300 lines, every line interview-explainable |
| UI (M4) | Streamlit | Zero frontend code; interactive pipeline dashboard |

## Quick Start

**Prerequisites:** Python 3.12+, `uv` or `pip`, SSH access to a GPU server running
Ollama (or an OpenAI-compatible API key as fallback).

```bash
# 1. Clone and install
git clone <repo-url> alpha-agent
cd alpha-agent
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env — set LLM_PROVIDER and OLLAMA_BASE_URL or OPENAI_API_KEY

# 3. (Ollama) Open SSH tunnel to remote GPU server
ssh -N -L 11434:localhost:6006 -p <port> root@<server>

# 4. Run
alpha-agent "find short-term reversal factors"
```

### Fallback: OpenAI-compatible API

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

No code changes needed — `LLMClientFactory` reads `LLM_PROVIDER` at startup.

## Factor Expression DSL

The parser supports Qlib-compatible function calls and full infix arithmetic.

**Grammar (operator precedence low → high):**

```
expr    := compare
compare := add_sub ((">" | "<" | ">=" | "<=") add_sub)?
add_sub := term    (("+"|"-") term)*
term    := unary   (("*"|"/") unary)*
unary   := "-" unary | power
power   := atom    ("**" atom)?
atom    := NUMBER | "$"IDENT | IDENT"("arglist")" | "("expr")"
```

**Examples:**

```
Rank(-Delta($close, 5))                        # 5-day short-term reversal
Corr($close, $volume, 20)                      # 20-day price-volume correlation
($close - Mean($close, 20)) / Std($close, 20)  # 20-day z-score (infix form)
Rank($close / Ref($close, 5) - 1)              # 5-day momentum
```

**Available operators:**

| Category | Operators |
|----------|-----------|
| Time-series | `Ref`, `Mean`, `Sum`, `Std`, `Var`, `Max`, `Min`, `Delta`, `EMA`, `WMA`, `Corr`, `Cov`, `Skew`, `Kurt`, `Med`, `Slope`, `Count` |
| Cross-sectional | `Rank`, `Zscore` |
| Elementwise | `Abs`, `Sign`, `Log`, `If` |
| Features | `$open`, `$close`, `$high`, `$low`, `$volume`, `$amount` |

## Project Structure

```
alpha-agent/
├── alpha_agent/
│   ├── agents/               # HypothesisAgent, FactorAgent, BacktestAgent, EvalAgent
│   ├── factor_engine/        # parser.py, evaluator.py, ast_nodes.py, regularizer.py
│   ├── data/                 # AKShareProvider, ParquetCache, CSI300Universe
│   ├── backtest/             # BacktestEngine, MetricsCalculator
│   ├── pipeline/             # orchestrator.py, state.py, registry.py
│   ├── llm/                  # OllamaClient, OpenAIClient, LLMClientFactory
│   ├── report/               # HTMLReportGenerator (M4)
│   └── ui/                   # Streamlit app (M4)
├── tests/                    # 90+ test cases across all modules
├── .env.example
├── pyproject.toml
└── status.json
```

## Development

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=alpha_agent --cov-report=term-missing

# Exclude slow tests that hit external networks
pytest -m "not slow"

# Lint
ruff check .
```

Current test coverage: **90+ tests** across parser (41), evaluator (34),
backtest engine (18), and agent/pipeline mocks.

## Roadmap

| Milestone | Description | Status |
|-----------|-------------|--------|
| M1 | Factor engine (parser, evaluator, backtest) | Done |
| M2 | LLM integration (Ollama, Gemma 4 26B, HypothesisAgent, FactorAgent) | Done |
| M3 | Multi-agent loop (BacktestAgent, EvalAgent, FactorRegistry) | In progress |
| M4 | Streamlit UI + HTML report generation | Planned |
| M5 | Polish, 80% coverage, CLI, error hardening | Planned |

## License

MIT
