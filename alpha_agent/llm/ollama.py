"""Ollama LLM client — calls remote/local Ollama via HTTP API."""

from __future__ import annotations

import httpx

from alpha_agent.llm.base import LLMClient, LLMResponse, Message


class OllamaClient(LLMClient):
    """Talks to Ollama's /api/chat endpoint.

    Supports both local and remote Ollama instances.
    Remote usage: set base_url to SSH-tunneled address (e.g., http://localhost:11434).
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma4:26b") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120.0)

    async def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        msg = data["message"]
        content = msg.get("content", "")

        # Gemma 4 thinking models may put output in "thinking" when content is empty
        if not content.strip() and msg.get("thinking"):
            content = self._extract_from_thinking(msg["thinking"])

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    @staticmethod
    def _extract_from_thinking(thinking: str) -> str:
        """Extract usable content from thinking field when content is empty.

        Gemma 4 sometimes places the final answer inside a ```json block
        within the thinking field.  We try to find the last such block.
        Falls back to returning the full thinking text.
        """
        import re

        # Look for the last ```json ... ``` block
        blocks = re.findall(r"```(?:json)?\s*\n(.*?)```", thinking, re.DOTALL)
        if blocks:
            return blocks[-1].strip()

        # Look for raw JSON object
        json_match = re.search(r"\{[\s\S]*\}", thinking)
        if json_match:
            return json_match.group(0).strip()

        return thinking.strip()

    async def is_available(self) -> bool:
        try:
            response = await self._client.get("/api/version")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def close(self) -> None:
        await self._client.aclose()
