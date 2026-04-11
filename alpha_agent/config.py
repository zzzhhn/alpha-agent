"""Application configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All config is loaded from environment variables or .env file."""

    # LLM provider
    llm_provider: Literal["ollama", "openai"] = "ollama"

    # Ollama settings (remote server via SSH tunnel or direct)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:26b"

    # OpenAI-compatible API settings (fallback)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

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
    fastapi_port: int = 8000
    dashboard_tickers: list[str] = ["NVDA", "AAPL", "TSLA"]
    dashboard_cache_ttl_seconds: int = 300
    model_dir: Path = Path("data/models")

    model_config = {
        "env_file": Path(__file__).resolve().parent.parent / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> Settings:
    """Create settings instance (reads .env on each call)."""
    return Settings()
