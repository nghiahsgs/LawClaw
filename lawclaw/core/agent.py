"""Executive branch — core agent loop with governance integration."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.config import Config
from lawclaw.core.judicial import JudicialBranch, Verdict
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.core.llm import LLMClient, ToolCall
from lawclaw.core.tools import ToolRegistry
from lawclaw.db import add_message, get_history


class Agent:
    def __init__(
        self,
        config: Config,
        conn: sqlite3.Connection,
        legislative: LegislativeBranch,
        judicial: JudicialBranch,
        tools: ToolRegistry,
        llm: LLMClient,
    ) -> None:
        self._config = config
        self._conn = conn
        self._legislative = legislative
        self._judicial = judicial
        self._tools = tools
        self._llm = llm

        # Pre-load constitution and laws once
        constitution_path = Path(config.constitution_path)
        if not constitution_path.is_absolute():
            # Resolve relative to config dir
            constitution_path = Path.home() / ".lawclaw" / config.constitution_path
        self._constitution = legislative.load_constitution(constitution_path)

        laws_dir = Path.home() / ".lawclaw" / "laws"
        self._laws = legislative.load_laws(laws_dir)

    async def process(
        self,
        message: str,
        session_key: str,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """
        Process a user message through the governed agent loop.

        on_progress(tool_name, args_preview, result_preview) is called after each tool execution.
        Returns the final assistant response string.
        """
        # 1. Load history
        history = get_history(self._conn, session_key, limit=self._config.memory_window)

        # 2. Build messages list
        system_prompt = self._build_system_prompt()
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        tool_defs = self._tools.get_definitions()
        tools_used: list[str] = []

        # 3. Agent loop
        for iteration in range(self._config.max_iterations):
            logger.debug("Agent iteration {}/{}", iteration + 1, self._config.max_iterations)

            response = await self._llm.chat(messages, tools=tool_defs if tool_defs else None)

            if response.tool_calls:
                # Build assistant message with tool_calls for the conversation
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": str(tc.arguments)},
                        }
                        for tc in response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                # Execute each tool call
                for tc in response.tool_calls:
                    verdict = self._judicial.pre_check(tc.name, tc.arguments, self._legislative)

                    if not verdict.allowed:
                        result_str = f"[BLOCKED] {verdict.reason}"
                        logger.warning("Tool '{}' blocked: {}", tc.name, verdict.reason)
                    else:
                        # Pass context to tools that need it
                        spawn_tool = self._tools.get("spawn_subagent")
                        if spawn_tool and hasattr(spawn_tool, "set_session_key"):
                            spawn_tool.set_session_key(session_key)
                        cron_tool = self._tools.get("manage_cron")
                        if cron_tool and hasattr(cron_tool, "set_chat_id"):
                            # Extract chat ID from session_key (e.g. "telegram:123456:v0" → "123456")
                            parts = session_key.split(":")
                            if len(parts) >= 2:
                                cron_tool.set_chat_id(parts[1])
                        result_str = await self._tools.execute(tc.name, tc.arguments)
                        tools_used.append(tc.name)
                        logger.debug("Tool '{}' executed, result length={}", tc.name, len(result_str))

                    self._judicial.log_action(session_key, tc.name, tc.arguments, result_str, verdict)

                    if on_progress:
                        try:
                            on_progress(tc.name, str(tc.arguments)[:200], result_str[:200])
                        except Exception:
                            logger.exception("on_progress callback raised")

                    # Append tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

                # Loop back to LLM with tool results
                continue

            # No tool calls — final response
            final_content = response.content or ""

            # 4. Persist user + assistant messages
            add_message(self._conn, session_key, "user", message)
            add_message(
                self._conn,
                session_key,
                "assistant",
                final_content,
                tools_used=tools_used or None,
            )

            return final_content

        # Exceeded max iterations
        fallback = "I reached the maximum number of reasoning steps. Please try a simpler request."
        add_message(self._conn, session_key, "user", message)
        add_message(self._conn, session_key, "assistant", fallback)
        return fallback

    def _build_system_prompt(self) -> str:
        """Combine constitution + laws + tool list + personality."""
        parts: list[str] = []

        if self._constitution:
            parts.append(f"# Constitution\n\n{self._constitution}")

        if self._laws:
            parts.append(f"# Laws\n\n{self._laws}")

        tool_names = self._tools.list_names()
        if tool_names:
            tool_list = "\n".join(f"- {n}" for n in tool_names)
            parts.append(f"# Available Tools\n\n{tool_list}")

        parts.append(
            "# Personality\n\n"
            "You are LawClaw, a governed AI agent. You operate within the boundaries "
            "defined by the constitution and laws above. You are helpful, precise, and transparent. "
            "You always disclose when a tool call was blocked and explain why."
        )

        return "\n\n---\n\n".join(parts)
