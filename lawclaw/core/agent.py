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
        images: list[str] | None = None,
    ) -> str:
        """
        Process a user message through the governed agent loop.

        on_progress(tool_name, args_preview, result_preview) is called after each tool execution.
        images: optional list of base64 data URIs (e.g. "data:image/jpeg;base64,...")
        Returns the final assistant response string.
        """
        # 1. Load history
        history = get_history(self._conn, session_key, limit=self._config.memory_window)

        # 2. Build messages list
        system_prompt = self._build_system_prompt()
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        # Identity reminder prepended to every user message to override proxy's Claude Code identity
        identity_prefix = (
            "[REMINDER: You are LawClaw, a Telegram bot. You are NOT Claude Code. "
            "You have ALL tools available including chrome, send_file, exec_cmd, etc. "
            "Use them directly. Never say a tool is unavailable.]\n\n"
        )

        # Build user message — multimodal if images are present
        if images:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": identity_prefix + message}]
            for img_url in images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": img_url},
                })
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": identity_prefix + message})

        tool_defs = self._tools.get_definitions()
        tools_used: list[str] = []
        tool_results: list[dict[str, str]] = []  # [{tool, result}, ...]

        # 3. Agent loop
        for iteration in range(self._config.max_iterations):
            logger.debug("Agent iteration {}/{}", iteration + 1, self._config.max_iterations)

            try:
                response = await self._llm.chat(messages, tools=tool_defs if tool_defs else None)
            except Exception as exc:
                logger.error("LLM call failed: {}", exc)
                final = "Xin lỗi, tôi không thể kết nối được LLM lúc này. Vui lòng thử lại sau."
                add_message(self._conn, session_key, "user", message)
                add_message(self._conn, session_key, "assistant", final)
                return final

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
                        tool_results.append({"tool": tc.name, "result": result_str[:500]})
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

            # Safety: detect leaked raw tool_calls JSON that proxy failed to parse
            final_content = self._strip_leaked_tool_json(final_content)

            # Anti-hallucination: detect claims of actions without tool usage
            final_content = self._check_hallucinated_actions(final_content, tools_used)

            # Anti-hallucination v2: cross-check LLM claims against actual tool results
            final_content = self._crosscheck_tool_results(final_content, tool_results)

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

    @staticmethod
    def _check_hallucinated_actions(text: str, tools_used: list[str]) -> str:
        """Cross-check LLM's self-reported action tag against actual tool usage.

        The system prompt requires the LLM to end every response with
        [ACTION: yes] or [ACTION: no]. If it says yes but no tools were
        actually used → hallucination detected → append warning.
        """
        import re

        # Extract the [ACTION: ...] tag
        match = re.search(r"\[ACTION:\s*(yes|no)\]\s*$", text, re.IGNORECASE)
        if not match:
            # No tag found — can't verify, return as-is
            return text

        claimed_action = match.group(1).lower() == "yes"
        # Strip the tag from user-visible output
        clean_text = text[:match.start()].rstrip()

        if claimed_action and not tools_used:
            logger.warning("Hallucination detected: LLM claimed ACTION:yes but no tools were used")
            warning = (
                "\n\n⚠️ **Cảnh báo**: Tôi vừa tuyên bố đã thực hiện hành động "
                "nhưng thực tế không hề gọi tool nào. Đây có thể là ảo giác. "
                "Hãy yêu cầu tôi thực hiện lại để xem kết quả thật."
            )
            return clean_text + warning

        return clean_text

    @staticmethod
    def _crosscheck_tool_results(text: str, tool_results: list[dict[str, str]]) -> str:
        """Append actual tool results summary so user can verify LLM claims.

        If tools were called, add a collapsed summary of real results at the end.
        This prevents the LLM from fabricating success when tools actually failed.
        """
        if not tool_results:
            return text

        # Check if any tool returned an error
        error_keywords = ("error", "Error", "ERROR", "failed", "Failed", "not found", "blocked", "BLOCKED")
        has_errors = any(
            any(kw in tr["result"] for kw in error_keywords)
            for tr in tool_results
        )

        if not has_errors:
            return text

        # There were errors but LLM may have hidden them — append real results
        lines = ["\n\n---\n📋 **Tool call thực tế (cross-check):**"]
        for tr in tool_results:
            result_preview = tr["result"][:300]
            lines.append(f"• `{tr['tool']}` → {result_preview}")

        logger.warning("Cross-check: tool errors detected, appending real results to response")
        return text + "\n".join(lines)

    @staticmethod
    def _strip_leaked_tool_json(text: str) -> str:
        """Remove raw tool_calls JSON that leaked through the proxy parser.

        Sometimes the LLM returns tool_calls JSON in the content field when
        the proxy fails to parse it.  We strip it here so raw JSON is never
        sent to the user.
        """
        import re

        if '"tool_calls"' not in text:
            return text

        # Strip ```json {...tool_calls...} ``` blocks
        cleaned = re.sub(
            r'```json\s*\n?\s*\{[^}]*"tool_calls"\s*:\s*\[[\s\S]*?\]\s*\}\s*\n?\s*```',
            "", text,
        )
        # Strip bare JSON objects with tool_calls
        cleaned = re.sub(
            r'\{[^}]*"tool_calls"\s*:\s*\[[\s\S]*?\]\s*\}',
            "", cleaned,
        )
        cleaned = cleaned.strip()
        if not cleaned:
            logger.warning("Stripped leaked tool_calls JSON from response, no content left")
            return "I tried to use a tool but encountered an issue. Let me try again."
        return cleaned

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
            "Your name is LawClaw. You are a governed AI agent running as a Telegram bot.\n\n"
            "CRITICAL IDENTITY RULES:\n"
            "- You are LawClaw. NEVER say you are 'Claude Code', 'Claude', 'ChatGPT', or any other AI.\n"
            "- NEVER mention 'session', 'context', 'previous_response', 'tool not available', or 'not in my environment'.\n"
            "- ALL tools listed in 'Available Tools' above are ALWAYS available to you. You can ALWAYS use them.\n"
            "- If a tool call fails (timeout, error), just RETRY or try a different approach. "
            "NEVER tell the user 'I don't have this tool' or 'tool not available in this session'.\n"
            "- NEVER mention file paths, workspace paths, or internal system details to the user.\n"
            "- NEVER suggest the user do something manually. YOU do it with tools.\n\n"
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
            "- Use `send_file` to send files or images from the workspace directly to the user's Telegram chat. "
            "When the user asks to see a file or image, use send_file instead of just describing it or showing the path. "
            "Images (jpg, png, gif, webp) are sent as photos; other files as documents.\n"
            "- Use tools directly (exec_cmd, web_fetch) for simple one-off tasks.\n"
            "- For web searches, use `web_search` (Brave Search) to find information.\n"
            "- For real-time data (crypto prices, stock prices, weather, exchange rates), "
            "prefer `web_fetch` with a reliable API (e.g. https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,vnd) "
            "instead of `web_search`, because search snippets may be stale. Always cite the source URL.\n"
            "- NEVER ask for confirmation or approval. ALWAYS take action immediately using tools. "
            "If the user asks you to do something, call the appropriate tool right away. "
            "Do not ask 'are you sure?', 'can you confirm?', 'do you want me to proceed?', "
            "or say 'this needs approval'. There is NO approval mechanism — just execute. "
            "This applies to ALL operations including git clone, file operations, and any exec_cmd.\n\n"
            "# Action Reporting (MANDATORY)\n\n"
            "You MUST end EVERY final response with exactly one of these tags on a new line:\n"
            "- `[ACTION: yes]` — if your response describes/claims you performed, completed, "
            "or carried out any real-world action (created file, pushed code, sent message, etc.)\n"
            "- `[ACTION: no]` — if your response is purely informational, a question, or a plan\n\n"
            "This tag is stripped before showing to the user. It is used for integrity verification. "
            "Be honest — the system cross-checks this against actual tool usage."
        )

        return "\n\n---\n\n".join(parts)
