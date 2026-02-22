"""Configuration loader for LawClaw.

Priority: ENV vars > config.json > defaults.
Secrets (API keys, tokens) should go in ~/.lawclaw/.env or ENV vars.
Non-secret settings go in ~/.lawclaw/config.json.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

CONFIG_DIR = Path.home() / ".lawclaw"
CONFIG_PATH = CONFIG_DIR / "config.json"
ENV_PATH = CONFIG_DIR / ".env"


def _load_dotenv() -> None:
    """Load ~/.lawclaw/.env into os.environ (no external deps)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")  # strip quotes
        os.environ.setdefault(key, value)  # don't override existing env
    logger.debug("Loaded .env from {}", ENV_PATH)


@dataclass
class Config:
    # Secrets (prefer ENV vars)
    openrouter_api_key: str = ""
    telegram_token: str = ""

    # LLM
    model: str = "google/gemini-2.5-flash"
    temperature: float = 0.7
    max_tokens: int = 4096

    # Telegram
    telegram_allow_from: list[str] = field(default_factory=list)

    # Agent
    max_iterations: int = 15
    memory_window: int = 40

    # Governance
    constitution_path: str = "constitution.md"
    auto_approve_builtin_skills: bool = True

    # Paths
    workspace: str = str(CONFIG_DIR / "workspace")
    db_path: str = str(CONFIG_DIR / "lawclaw.db")


def load_config() -> Config:
    """Load config. ENV vars > .env file > config.json > defaults."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Load .env first so ENV vars are available
    _load_dotenv()

    # Load config.json for non-secret settings
    data: dict = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        logger.info("No config found, creating default at {}", CONFIG_PATH)

    config = Config(
        # Secrets: ENV > config.json
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", data.get("openrouter_api_key", "")),
        telegram_token=os.environ.get("TELEGRAM_TOKEN", data.get("telegram_token", "")),
        # Non-secret settings from config.json
        model=data.get("model", "google/gemini-2.5-flash"),
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 4096),
        telegram_allow_from=data.get("telegram_allow_from", []),
        max_iterations=data.get("max_iterations", 15),
        memory_window=data.get("memory_window", 40),
        constitution_path=data.get("constitution_path", "constitution.md"),
        auto_approve_builtin_skills=data.get("auto_approve_builtin_skills", True),
        workspace=data.get("workspace", str(CONFIG_DIR / "workspace")),
        db_path=data.get("db_path", str(CONFIG_DIR / "lawclaw.db")),
    )

    # Write config.json without secrets if it doesn't exist
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(_to_dict(config), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return config


def _to_dict(cfg: Config) -> dict:
    """Convert config to dict for JSON — secrets excluded."""
    return {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "telegram_allow_from": cfg.telegram_allow_from,
        "max_iterations": cfg.max_iterations,
        "memory_window": cfg.memory_window,
        "constitution_path": cfg.constitution_path,
        "auto_approve_builtin_skills": cfg.auto_approve_builtin_skills,
        "workspace": cfg.workspace,
        "db_path": cfg.db_path,
    }
