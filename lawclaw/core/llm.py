"""LLM client for LawClaw — supports Claude Max proxy and OpenRouter.

Providers:
  - claude-proxy: Local Claude Max proxy at localhost:3456 (requires subscription)
  - openrouter: OpenRouter API (supports Gemini, Claude, etc.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from lawclaw.config import Config

CLAUDE_PROXY_URL = "http://127.0.0.1:3456/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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


class LLMClient:
    def __init__(self, config: Config) -> None:
        self._config = config
        provider = config.llm_provider.lower()

        if provider == "openrouter":
            if not config.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
            self._url = OPENROUTER_URL
            self._headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.openrouter_api_key}",
            }
            self._model = config.model  # e.g. "google/gemini-2.5-pro"
        else:
            # Default: claude-proxy
            self._url = CLAUDE_PROXY_URL
            self._headers = {"Content-Type": "application/json"}
            # Strip '-local' suffix: "claude-opus-4-local" -> "claude-opus-4"
            self._model = config.model.removesuffix("-local").removesuffix("-LOCAL")

        logger.info("LLM provider: {} | model: {} | url: {}", provider, self._model, self._url)

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

        logger.debug("LLM call: model={} messages={}", self._model, len(messages))

        async with httpx.AsyncClient(timeout=1800.0) as client:
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
