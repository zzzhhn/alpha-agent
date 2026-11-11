"""SET-2: a bot model call marks the stored BYOK credential as used."""
from unittest.mock import AsyncMock

from alpha_agent.llm.base import LLMResponse
from alpha_agent.paper import bot_runner, bot_store
from alpha_agent.paper.bot_models import BotConfig


async def test_model_decision_updates_last_used_after_response(monkeypatch):
    calls = []

    class Pool:
        async def fetchval(self, sql, *args):
            return 7  # owner user id

        async def execute(self, sql, *args):
            calls.append((sql, args))

    monkeypatch.setenv("BYOK_MASTER_KEY", "unused")
    monkeypatch.setattr(bot_store, "credential", AsyncMock(return_value={
        "ciphertext": b"c", "nonce": b"n", "base_url": None, "provider": "kimi", "model": "m"}))
    monkeypatch.setattr(bot_runner, "decrypt", lambda *a: "key")
    fake = type("Client", (), {})()
    fake.chat = AsyncMock(return_value=LLMResponse("{}", "m", 1, 1))
    fake.close = AsyncMock()
    monkeypatch.setattr(bot_runner, "_build_byok_client", lambda *a: fake)
    config = BotConfig(provider="kimi", model="m")
    await bot_runner.model_decision(Pool(), {"account_id": 1, "llm_calls": 0}, {}, config)
    assert calls and "last_used_at=now()" in calls[0][0]
    assert calls[0][1] == (7, "kimi")


async def test_failed_model_call_does_not_mark_used(monkeypatch):
    calls = []

    class Pool:
        async def fetchval(self, sql, *args):
            return 7

        async def execute(self, sql, *args):
            calls.append(sql)

    monkeypatch.setenv("BYOK_MASTER_KEY", "unused")
    monkeypatch.setattr(bot_store, "credential", AsyncMock(return_value={
        "ciphertext": b"c", "nonce": b"n", "base_url": None}))
    monkeypatch.setattr(bot_runner, "decrypt", lambda *a: "key")
    fake = type("Client", (), {})()
    fake.chat = AsyncMock(side_effect=RuntimeError("provider down"))
    fake.close = AsyncMock()
    monkeypatch.setattr(bot_runner, "_build_byok_client", lambda *a: fake)
    try:
        await bot_runner.model_decision(Pool(), {"account_id": 1, "llm_calls": 0}, {}, BotConfig(provider="kimi", model="m"))
    except RuntimeError:
        pass
    assert calls == []
