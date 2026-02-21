"""Sub-agent spawner — lightweight single-task agent with no memory persistence."""

from __future__ import annotations

import sqlite3

from loguru import logger

from lawclaw.config import Config
from lawclaw.core.agent import Agent
from lawclaw.core.judicial import JudicialBranch
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.core.llm import LLMClient
from lawclaw.core.tools import ToolRegistry
from lawclaw.db import get_history, add_message


class _NoopConn:
    """Fake connection that silently swallows writes — subagents don't persist history."""

    def execute(self, *args, **kwargs):  # noqa: ANN001
        return _NoopCursor()

    def commit(self) -> None:
        pass


class _NoopCursor:
    def fetchone(self):  # noqa: ANN201
        return None

    def fetchall(self):  # noqa: ANN201
        return []


class _SubagentAgent(Agent):
    """Agent variant that uses a noop connection for message persistence."""

    async def process(self, message: str, session_key: str, on_progress=None) -> str:  # type: ignore[override]
        # Bypass DB history — subagents are stateless
        from lawclaw.config import Config
        from lawclaw.core.llm import LLMClient
        from lawclaw.db import get_history, add_message
        import sqlite3

        system_prompt = self._build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        tool_defs = self._tools.get_definitions()
        max_iter = min(self._config.max_iterations, 5)  # subagents: max 5 iterations

        for iteration in range(max_iter):
            logger.debug("Subagent iteration {}/{}", iteration + 1, max_iter)
            response = await self._llm.chat(messages, tools=tool_defs if tool_defs else None)

            if response.tool_calls:
                assistant_msg = {
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

                for tc in response.tool_calls:
                    verdict = self._judicial.pre_check(tc.name, tc.arguments, self._legislative)
                    if not verdict.allowed:
                        result_str = f"[BLOCKED] {verdict.reason}"
                    else:
                        result_str = await self._tools.execute(tc.name, tc.arguments)

                    self._judicial.log_action(session_key, tc.name, tc.arguments, result_str, verdict)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
                continue

            return response.content or ""

        return "Subagent reached iteration limit without a final answer."


class SubagentManager:
    """Creates and manages ephemeral sub-agents."""

    def __init__(
        self,
        config: Config,
        conn: sqlite3.Connection,
        legislative: LegislativeBranch,
        judicial: JudicialBranch,
        tools: ToolRegistry,
    ) -> None:
        self._config = config
        self._conn = conn
        self._legislative = legislative
        self._judicial = judicial
        self._tools = tools

    async def spawn(self, task: str, session_key: str) -> str:
        """Spawn a sub-agent for a single task. Returns result string."""
        llm = LLMClient(self._config)

        # Use a limited config for subagents
        sub_config = Config(
            openrouter_api_key=self._config.openrouter_api_key,
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            max_iterations=5,
            memory_window=0,
            constitution_path=self._config.constitution_path,
            workspace=self._config.workspace,
        )

        agent = _SubagentAgent(
            config=sub_config,
            conn=self._conn,
            legislative=self._legislative,
            judicial=self._judicial,
            tools=self._tools,
            llm=llm,
        )

        logger.info("Spawning subagent for task: {}", task[:80])
        result = await agent.process(task, session_key=session_key)
        logger.info("Subagent completed, result length={}", len(result))
        return result
