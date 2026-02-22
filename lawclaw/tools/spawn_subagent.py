"""Spawn sub-agent tool — lets the main agent delegate tasks to ephemeral workers."""

from __future__ import annotations

from typing import Any

from lawclaw.core.tools import Tool


class SpawnSubagentTool(Tool):
    """Tool that the main agent LLM calls to delegate a task to a sub-agent."""

    name = "spawn_subagent"
    description = (
        "Delegate a task to a sub-agent. The sub-agent runs independently with its own "
        "LLM context, executes tools if needed, and returns a text result. "
        "Use this for any non-trivial task: web searches, command execution, analysis, etc. "
        "The sub-agent has access to web_search, web_fetch, and exec_cmd tools."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Clear description of the task for the sub-agent to perform.",
            },
        },
        "required": ["task"],
    }

    def __init__(self) -> None:
        # SubagentManager is injected after construction via set_manager()
        self._manager: Any = None
        self._session_key: str = ""

    def set_manager(self, manager: Any) -> None:
        self._manager = manager

    def set_session_key(self, session_key: str) -> None:
        self._session_key = session_key

    async def execute(self, task: str) -> str:  # type: ignore[override]
        if not self._manager:
            return "[ERROR] SubagentManager not configured."
        return await self._manager.spawn(task=task, session_key=self._session_key)
