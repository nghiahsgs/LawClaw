"""Multi-provider LLM client for LawClaw.

Supports OpenRouter (default) and Z.AI (Zhipu AI).
Provider auto-detected from model name: glm-* → Z.AI, else → OpenRouter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from lawclaw.config import Config

# Provider endpoints
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


def _detect_provider(model: str) -> str:
    """Auto-detect provider from model name."""
    lower = model.lower()
    if lower.startswith("glm-") or lower.startswith("z.ai/"):
        return "zai"
    return "openrouter"


class LLMClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._provider = _detect_provider(config.model)

        if self._provider == "zai":
            self._url = ZAI_URL
            self._headers = {
                "Authorization": f"Bearer {config.zai_api_key}",
                "Content-Type": "application/json",
            }
            # Strip provider prefix if present (e.g. "z.ai/glm-4.7" → "glm-4.7")
            self._model = config.model.split("/", 1)[-1] if "/" in config.model else config.model
        else:
            self._url = OPENROUTER_URL
            self._headers = {
                "Authorization": f"Bearer {config.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/lawclaw",
                "X-Title": "LawClaw",
                "Content-Type": "application/json",
            }
            self._model = config.model

        logger.info("LLM provider: {} | model: {}", self._provider, self._model)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send messages to LLM provider and return parsed response."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        logger.debug("LLM call: provider={} model={} messages={}", self._provider, self._model, len(messages))

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(self._url, headers=self._headers, json=payload)
            if resp.status_code != 200:
                logger.error("LLM error {}: {}", resp.status_code, resp.text[:500])
                resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")
        content = message.get("content")

        tool_calls: list[ToolCall] = []
        raw_calls = message.get("tool_calls") or []
        for tc in raw_calls:
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool call arguments: {}", raw_args)
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=func["name"], arguments=args))

        logger.debug(
            "LLM response: finish_reason={} tool_calls={}", finish_reason, len(tool_calls)
        )
        return LLMResponse(content=content, tool_calls=tool_calls, finish_reason=finish_reason)
