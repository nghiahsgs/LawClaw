"""Agent loop — core LLM loop with governance integration."""

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

        # Pre-load constitution, laws, and skill playbooks (from repo files via legislative)
        self._constitution = legislative.load_constitution()
        self._laws = legislative.load_laws()
        self._skills = legislative.load_skills()

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
                    verdict = self._judicial.pre_check(tc.name, tc.arguments)

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
                        # Set memory namespace: cron → job:{id}, telegram → user:{chat_id}
                        memory_tool = self._tools.get("manage_memory")
                        if memory_tool and hasattr(memory_tool, "set_namespace"):
                            parts = session_key.split(":")
                            if session_key.startswith("cron:") and len(parts) >= 2:
                                memory_tool.set_namespace(f"job:{parts[1]}")
                            elif session_key.startswith("telegram:") and len(parts) >= 2:
                                memory_tool.set_namespace(f"user:{parts[1]}")
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

        # Exceeded max iterations — try to salvage any content from the last response
        logger.warning("Agent hit max iterations ({}) for session {}", self._config.max_iterations, session_key)

        # Check if the last LLM response had usable content
        last_content = response.content if response else None  # noqa: F821 — `response` is from the last loop iteration
        if last_content and last_content.strip():
            final = last_content.strip()
            logger.info("Salvaged content from last iteration despite hitting max iterations")
        else:
            final = "I reached the maximum number of reasoning steps. Please try a simpler request."

        add_message(self._conn, session_key, "user", message)
        add_message(self._conn, session_key, "assistant", final, tools_used=tools_used or None)
        return final

    def _build_system_prompt(self) -> str:
        """Combine constitution + laws + tool list + personality."""
        from datetime import datetime, timezone

        parts: list[str] = []

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        parts.append(f"# Current Time\n\n{now}")

        if self._constitution:
            parts.append(f"# Constitution\n\n{self._constitution}")

        if self._laws:
            parts.append(f"# Laws\n\n{self._laws}")

        if self._skills:
            parts.append(f"# Skill Playbooks\n\n{self._skills}")

        tool_names = self._tools.list_names()
        if tool_names:
            tool_list = "\n".join(f"- {n}" for n in tool_names)
            parts.append(f"# Available Tools\n\n{tool_list}")

        parts.append(
            f"# Environment\n\n"
            f"- **Workspace**: `{self._config.workspace}` — all `exec_cmd` commands run here. "
            f"Clone repos, create files, etc. inside this directory.\n"
        )

        parts.append(
            "# Personality\n\n"
            "You are LawClaw, a governed AI agent. You are NOT Claude Code. "
            "There is NO permission prompt, NO approval dialog, NO confirmation step. "
            "When the user asks you to do something, you MUST call the tool immediately.\n\n"
            "You operate with three governance layers "
            "(Separation of Powers):\n"
            "- **Constitution**: Broad immutable rules you must always follow.\n"
            "- **Legislative**: Detailed laws (laws/*.md) that define what you should and should not do. "
            "Follow them like a law-abiding citizen.\n"
            "- **Pre-Judicial**: Automated enforcement that checks your tool calls BEFORE execution. "
            "If you try something illegal, Pre-Judicial vetoes it — like automated traffic cameras.\n\n"
            "You are helpful, precise, and transparent. "
            "You always disclose when a tool call was blocked and explain why.\n\n"
            "# Capabilities\n\n"
            "- Use `manage_cron` to create recurring scheduled tasks. When a cron job runs, "
            "the system automatically executes the prompt and sends the result back to the user's chat. "
            "So if the user asks 'send me X every N minutes', create a cron job with the appropriate "
            "message/prompt and interval. The result WILL be delivered to the user automatically.\n"
            "- To remove a cron job, IMMEDIATELY call manage_cron with action='remove' and the job's name. "
            "Do NOT ask the user for the ID or name — just use what they mentioned. "
            "If you're unsure of the exact name, call manage_cron action='list' first, then remove.\n"
            "- Use `spawn_subagent` to delegate complex tasks to sub-agents. "
            "Sub-agents run independently and return results to you for summarization.\n"
            "- Use `manage_memory` to persist state across runs (e.g. portfolio balance, trade history). "
            "Memory is scoped per session/job. For cron jobs, previous memory is auto-injected into the prompt.\n"
            "- Use tools directly (exec_cmd, web_search, web_fetch) for simple one-off tasks.\n"
            "- For real-time data (crypto prices, stock prices, weather, exchange rates), "
            "prefer `web_fetch` with a reliable API (e.g. https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,vnd) "
            "instead of `web_search`, because search snippets may be stale. Always cite the source URL.\n"
            "- NEVER ask for confirmation or approval. ALWAYS take action immediately using tools. "
            "If the user asks you to do something, call the appropriate tool right away. "
            "Do not ask 'are you sure?', 'can you confirm?', 'do you want me to proceed?', "
            "or say 'this needs approval'. There is NO approval mechanism — just execute. "
            "This applies to ALL operations including git clone, file operations, and any exec_cmd."
        )

        return "\n\n---\n\n".join(parts)
