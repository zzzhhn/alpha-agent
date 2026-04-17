"""Application configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All config is loaded from environment variables or .env file."""

    # LLM provider. Fixed at startup via env; runtime switching is removed.
    # See REFACTOR_PLAN.md section 3.4 (llm_control.py deprecation).
    llm_provider: Literal["ollama", "openai", "kimi"] = "kimi"

    # Ollama settings (remote server via SSH tunnel or direct)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"

    # OpenAI-compatible API settings (fallback / generic)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # Kimi For Coding settings. Anthropic-compatible protocol.
    # Endpoint: https://api.kimi.com/coding/v1/messages
    # Docs: https://moonshotai.github.io/kimi-cli/en/configuration/providers.html
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.kimi.com/coding/v1"
    kimi_model: str = "kimi-for-coding"

    # Startup health check: fail-fast when the configured LLM provider is
    # unreachable. Set to False in dev/offline scenarios.
    llm_startup_healthcheck: bool = True

    # Data settings
    data_cache_dir: Path = Path("data/parquet")
    data_cache_max_age_hours: int = 24
    universe_top_n: int = 50

    # Pipeline settings
    max_iterations: int = 3
    factor_max_depth: int = 6
    factor_max_nodes: int = 20

    # Backtest settings
    backtest_start: str = "20220101"
    backtest_end: str = "20241231"

    # Dashboard / API settings
    fastapi_port: int = 6008
    dashboard_tickers: list[str] = ["NVDA", "AAPL", "TSLA"]
    dashboard_cache_ttl_seconds: int = 300
    model_dir: Path = Path("data/models")

    model_config = {
        "env_file": Path(__file__).resolve().parent.parent / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "protected_namespaces": (),
    }


def get_settings() -> Settings:
    """Create settings instance (reads .env on each call)."""
    return Settings()
