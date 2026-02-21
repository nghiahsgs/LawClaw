"""Tool registry for LawClaw — manages all agent tools."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class Tool(ABC):
    """Base class for all LawClaw tools."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
        logger.debug("Tool registered: {}", tool.name)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions in OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name with given args, return string result."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: tool '{name}' not found in registry."
        try:
            result = await tool.execute(**args)
            return result
        except Exception as exc:
            logger.exception("Tool '{}' raised an exception", name)
            return f"Error executing '{name}': {exc}"

    def list_names(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())
