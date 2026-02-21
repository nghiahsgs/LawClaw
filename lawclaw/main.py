"""LawClaw entry point — wire everything together and run."""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from loguru import logger

from lawclaw.config import CONFIG_DIR, load_config
from lawclaw.core.agent import Agent
from lawclaw.core.cron import CronService
from lawclaw.core.judicial import JudicialBranch
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.core.llm import LLMClient
from lawclaw.core.tools import ToolRegistry
from lawclaw.db import get_connection, init_db
from lawclaw.telegram import TelegramBot
from lawclaw.tools.exec_cmd import ExecCmdTool
from lawclaw.tools.web_fetch import WebFetchTool
from lawclaw.tools.web_search import WebSearchTool

# Constitution source (bundled with package)
BUNDLED_CONSTITUTION = Path(__file__).parent.parent / "constitution.md"


def _setup_workspace() -> None:
    """Create default directories and copy constitution if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "laws").mkdir(exist_ok=True)
    (CONFIG_DIR / "workspace").mkdir(exist_ok=True)

    # Copy bundled constitution to config dir if not exists
    target = CONFIG_DIR / "constitution.md"
    if not target.exists() and BUNDLED_CONSTITUTION.exists():
        shutil.copy2(BUNDLED_CONSTITUTION, target)
        logger.info("Constitution copied to {}", target)


async def run_gateway() -> None:
    """Run the full LawClaw gateway (Telegram + Cron)."""
    config = load_config()

    if not config.openrouter_api_key:
        logger.error("OpenRouter API key not configured. Edit ~/.lawclaw/config.json")
        sys.exit(1)

    _setup_workspace()

    # Database
    conn = get_connection(Path(config.db_path))
    init_db(conn)

    # Three branches of government
    legislative = LegislativeBranch(conn)
    judicial = JudicialBranch(conn, workspace=Path(config.workspace))
    llm = LLMClient(config)

    # Tools (Executive's instruments)
    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(WebFetchTool())
    tools.register(ExecCmdTool(workspace=config.workspace))

    # Register built-in tools as approved
    if config.auto_approve_builtin_skills:
        legislative.register_builtin(tools.list_names())

    # Agent (Executive branch)
    agent = Agent(
        config=config, conn=conn,
        legislative=legislative, judicial=judicial,
        tools=tools, llm=llm,
    )

    # Cron
    async def on_cron_job(job_id: str, message: str, chat_id: str) -> str | None:
        session_key = f"cron:{job_id}"
        return await agent.process(message=message, session_key=session_key)

    cron = CronService(conn=conn, on_job=on_cron_job)
    cron.start()

    # Telegram
    bot = TelegramBot(
        config=config, agent=agent, conn=conn,
        legislative=legislative, judicial=judicial,
    )

    logger.info("🏛️ LawClaw gateway starting...")
    logger.info("   Model: {}", config.model)
    logger.info("   Workspace: {}", config.workspace)
    logger.info("   Approved tools: {}", ", ".join(tools.list_names()))

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

    legislative = LegislativeBranch(conn)
    judicial = JudicialBranch(conn, workspace=Path(config.workspace))
    llm = LLMClient(config)

    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(WebFetchTool())
    tools.register(ExecCmdTool(workspace=config.workspace))

    if config.auto_approve_builtin_skills:
        legislative.register_builtin(tools.list_names())

    agent = Agent(
        config=config, conn=conn,
        legislative=legislative, judicial=judicial,
        tools=tools, llm=llm,
    )

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
        config = load_config()
        print(f"🏛️ LawClaw initialized at {CONFIG_DIR}")
        print(f"   Edit config: {CONFIG_DIR / 'config.json'}")
        print(f"   Constitution: {CONFIG_DIR / 'constitution.md'}")

    elif cmd == "gateway":
        asyncio.run(run_gateway())

    elif cmd == "chat":
        if len(sys.argv) < 3:
            print("Usage: lawclaw chat 'your message'")
            sys.exit(1)
        message = " ".join(sys.argv[2:])
        asyncio.run(run_cli(message))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
