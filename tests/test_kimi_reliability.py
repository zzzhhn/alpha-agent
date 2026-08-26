from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from alpha_agent.core.exceptions import LLMEmptyResponseError
from alpha_agent.llm._legacy.kimi import KimiClient
from alpha_agent.llm.base import Message


def _response(content: list[dict], *, output_tokens: int, stop: str = "end_turn"):
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.kimi.com/coding/v1/messages"),
        json={
            "model": "kimi-for-coding",
            "content": content,
            "stop_reason": stop,
            "usage": {"input_tokens": 8, "output_tokens": output_tokens},
        },
    )


@pytest.mark.asyncio
async def test_kimi_retries_empty_reasoning_budget_with_more_room() -> None:
    client = KimiClient(api_key="test-only")
    fake = AsyncMock()
    fake.post = AsyncMock(side_effect=[
        _response([], output_tokens=4096, stop="max_tokens"),
        _response([{"type": "text", "text": "OK"}], output_tokens=4300),
    ])
    fake.aclose = AsyncMock()
    await client._client.aclose()
    client._client = fake

    result = await client.chat([Message(role="user", content="test")], max_tokens=128)

    assert result.content == "OK"
    assert [call.kwargs["json"]["max_tokens"] for call in fake.post.call_args_list] == [4096, 8192]


@pytest.mark.asyncio
async def test_kimi_empty_after_retry_is_an_explicit_failure() -> None:
    client = KimiClient(api_key="test-only")
    fake = AsyncMock()
    fake.post = AsyncMock(side_effect=[
        _response([], output_tokens=4096, stop="max_tokens"),
        _response([], output_tokens=8192, stop="max_tokens"),
    ])
    fake.aclose = AsyncMock()
    await client._client.aclose()
    client._client = fake

    with pytest.raises(LLMEmptyResponseError):
        await client.chat([Message(role="user", content="test")], max_tokens=128)
