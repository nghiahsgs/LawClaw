"""LawClaw entry point — wire everything together and run."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

from loguru import logger

from lawclaw.config import CONFIG_DIR, Config, load_config
from lawclaw.core.agent import Agent
from lawclaw.core.cron import CronService
from lawclaw.core.judicial import JudicialBranch
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.core.llm import LLMClient
from lawclaw.core.subagent import SubagentManager
from lawclaw.core.tools import ToolRegistry
from lawclaw.db import get_connection, init_db
from lawclaw.telegram import TelegramBot
from lawclaw.tools.exec_cmd import ExecCmdTool
from lawclaw.tools.manage_cron import ManageCronTool
from lawclaw.tools.manage_memory import ManageMemoryTool, load_memory_for_namespace
from lawclaw.tools.spawn_subagent import SpawnSubagentTool
from lawclaw.tools.web_fetch import WebFetchTool
from lawclaw.tools.chrome_cdp import ChromeCdpTool
from lawclaw.tools.web_search import WebSearchTool

# Repo root: where governance markdown files live
REPO_ROOT = Path(__file__).parent.parent


def _setup_workspace() -> None:
    """Create runtime directories."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "workspace").mkdir(exist_ok=True)


def _make_base_tools(workspace: str, chrome_cdp_port: int = 9222) -> ToolRegistry:
    """Create base tool registry (used by sub-agents — no spawn)."""
    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(WebFetchTool())
    tools.register(ExecCmdTool(workspace=workspace))
    tools.register(ChromeCdpTool(port=chrome_cdp_port))
    return tools


def _build_branches(conn: sqlite3.Connection, workspace: str) -> tuple[LegislativeBranch, JudicialBranch]:
    """Build both governance branches from repo markdown files."""
    legislative = LegislativeBranch(
        constitution_path=REPO_ROOT / "constitution.md",
        laws_dir=REPO_ROOT / "laws",
        skills_dir=REPO_ROOT / "skills",
    )
    judicial = JudicialBranch(
        conn=conn,
        judicial_path=REPO_ROOT / "judicial.md",
        workspace=Path(workspace),
    )
    return legislative, judicial


def _build_agent(
    config: Config,
    conn: sqlite3.Connection,
    legislative: LegislativeBranch,
    judicial: JudicialBranch,
    llm: LLMClient,
    cron: CronService | None = None,
) -> tuple[Agent, ManageCronTool | None]:
    """Build agent with all tools."""
    base_tools = _make_base_tools(config.workspace, config.chrome_cdp_port)

    subagent_mgr = SubagentManager(
        config=config, conn=conn,
        legislative=legislative, judicial=judicial,
        tools=base_tools,
    )

    main_tools = _make_base_tools(config.workspace, config.chrome_cdp_port)
    spawn_tool = SpawnSubagentTool()
    spawn_tool.set_manager(subagent_mgr)
    main_tools.register(spawn_tool)

    memory_tool = ManageMemoryTool(conn)
    main_tools.register(memory_tool)

    cron_tool = None
    if cron:
        cron_tool = ManageCronTool()
        cron_tool.set_cron(cron)
        main_tools.register(cron_tool)

    agent = Agent(
        config=config, conn=conn,
        legislative=legislative, judicial=judicial,
        tools=main_tools, llm=llm,
    )
    return agent, cron_tool


async def run_gateway() -> None:
    """Run the full LawClaw gateway (Telegram + Cron)."""
    config = load_config()
    _setup_workspace()

    conn = get_connection(Path(config.db_path))
    init_db(conn)

    legislative, judicial = _build_branches(conn, config.workspace)
    llm = LLMClient(config)

    cron = CronService(conn=conn)
    agent, cron_tool = _build_agent(config, conn, legislative, judicial, llm, cron=cron)

    bot = TelegramBot(
        config=config, agent=agent, conn=conn,
        legislative=legislative, judicial=judicial,
    )

    # Cron callback: run agent + send result to Telegram
    async def on_cron_job(job_id: str, message: str, chat_id: str) -> str | None:
        import time
        run_key = f"cron:{job_id}:{int(time.time())}"

        mem_tool = agent._tools.get("manage_memory")
        if mem_tool:
            mem_tool.set_namespace(f"job:{job_id}")

        job_memory = load_memory_for_namespace(conn, f"job:{job_id}")
        memory_section = ""
        if job_memory:
            memory_section = f"\n\nYour persisted memory from previous runs:\n{job_memory}\n"

        cron_prompt = (
            "[SCHEDULED TASK] You are executing an automated cron job.\n"
            "Your text response will be sent directly to the user's chat — "
            "just reply with the content, no tool needed to 'send' it.\n"
            "Only use tools if the task genuinely requires external data (e.g. web_search for prices, "
            "web_fetch for APIs). For creative/text-only tasks, respond directly WITHOUT calling any tools.\n"
            "Use manage_memory to save any state you need for next run."
            f"{memory_section}\n\nTask: {message}"
        )
        response = await agent.process(message=cron_prompt, session_key=run_key)
        if response and chat_id and bot._app:
            try:
                await bot._app.bot.send_message(chat_id=int(chat_id), text=response)
            except Exception as e:
                logger.error("Failed to send cron result to {}: {}", chat_id, e)
        return response

    cron.on_job = on_cron_job
    cron.start()

    logger.info("LawClaw gateway starting...")
    logger.info("   Model: {}", config.model)
    logger.info("   Workspace: {}", config.workspace)

    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        cron.stop()
        await bot.stop()
        conn.close()
        logger.info("LawClaw shutdown complete")


async def run_cli(message: str) -> None:
    """Process a single message via CLI (no Telegram)."""
    config = load_config()
    _setup_workspace()

    conn = get_connection(Path(config.db_path))
    init_db(conn)

    legislative, judicial = _build_branches(conn, config.workspace)
    llm = LLMClient(config)

    agent, _ = _build_agent(config, conn, legislative, judicial, llm)

    response = await agent.process(message=message, session_key="cli:direct")
    print(response)
    conn.close()


def cli() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  lawclaw gateway    — Start Telegram bot + Cron")
        print("  lawclaw chat MSG   — Send a single message")
        print("  lawclaw init       — Initialize config")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "init":
        _setup_workspace()
        load_config()
        print(f"LawClaw initialized at {CONFIG_DIR}")
        print(f"   Governance: {REPO_ROOT} (constitution.md, judicial.md, laws/, skills/)")

    elif cmd == "gateway":
        asyncio.run(run_gateway())

    elif cmd == "chat":
        if len(sys.argv) < 3:
            print("Usage: lawclaw chat 'your message'")
            sys.exit(1)
        asyncio.run(run_cli(" ".join(sys.argv[2:])))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
