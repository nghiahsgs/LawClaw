"""LLM client for LawClaw — supports Claude Max proxy, OpenRouter, and Alibaba Cloud.

Providers:
  - claude-proxy: Local Claude Max proxy at localhost:3456 (requires subscription)
  - openrouter: OpenRouter API (supports Gemini, Claude, etc.)
  - alibaba: Alibaba Cloud DashScope API (Qwen models)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds between retries
REQUEST_TIMEOUT = 300.0  # 5 min per attempt (was 30 min total)

from lawclaw.config import Config

CLAUDE_PROXY_URL = "http://127.0.0.1:3456/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ALIBABA_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
ALIBABA_CN_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


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
        elif provider in ("alibaba", "alibaba-cn"):
            if not config.alibaba_api_key:
                raise ValueError("ALIBABA_API_KEY is required when LLM_PROVIDER=alibaba")
            self._url = ALIBABA_CN_URL if provider == "alibaba-cn" else ALIBABA_URL
            self._headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.alibaba_api_key}",
            }
            self._model = config.model  # e.g. "qwen-plus", "qwen-turbo", "qwen-max"
        else:
            # Default: claude-proxy
            self._url = CLAUDE_PROXY_URL
            self._headers = {"Content-Type": "application/json"}
            # Strip '-local' suffix: "claude-opus-4-local" -> "claude-opus-4"
            self._model = config.model.removesuffix("-local").removesuffix("-LOCAL")

        self._provider = provider
        logger.info("LLM provider: {} | model: {} | url: {}", provider, self._model, self._url)

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def switch(self, provider: str, model: str, api_key: str = "") -> None:
        """Hot-swap provider and model at runtime."""
        provider = provider.lower()
        if provider == "openrouter":
            key = api_key or self._config.openrouter_api_key
            if not key:
                raise ValueError("OpenRouter API key required")
            self._url = OPENROUTER_URL
            self._headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
        elif provider in ("alibaba", "alibaba-cn"):
            key = api_key or self._config.alibaba_api_key
            if not key:
                raise ValueError("Alibaba API key required")
            self._url = ALIBABA_CN_URL if provider == "alibaba-cn" else ALIBABA_URL
            self._headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }
        elif provider == "claude-proxy":
            self._url = CLAUDE_PROXY_URL
            self._headers = {"Content-Type": "application/json"}
            model = model.removesuffix("-local").removesuffix("-LOCAL")
        else:
            raise ValueError(f"Unknown provider: {provider}")
        self._provider = provider
        self._model = model
        logger.info("LLM switched: provider={} model={}", provider, model)

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

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    resp = await client.post(self._url, headers=self._headers, json=payload)
                    if resp.status_code >= 500 or resp.status_code == 429:
                        # Server error or rate limit — retry
                        logger.warning(
                            "LLM attempt {}/{} got status {}, retrying in {}s",
                            attempt + 1, MAX_RETRIES, resp.status_code, RETRY_DELAYS[attempt],
                        )
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    if resp.status_code != 200:
                        logger.error("LLM error {}: {}", resp.status_code, resp.text[:500])
                        resp.raise_for_status()
                    data = resp.json()
                return self._parse_response(data)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "LLM attempt {}/{} timed out after {}s, retrying in {}s",
                    attempt + 1, MAX_RETRIES, REQUEST_TIMEOUT,
                    RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) - 1 else "N/A",
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
            except (httpx.ConnectError, httpx.ReadError) as exc:
                last_error = exc
                logger.warning(
                    "LLM attempt {}/{} connection error: {}, retrying in {}s",
                    attempt + 1, MAX_RETRIES, exc,
                    RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) - 1 else "N/A",
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        # All retries exhausted
        raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")

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
