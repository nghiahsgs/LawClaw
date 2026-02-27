"""Configuration loader for LawClaw.

Priority: ENV vars > .env file > defaults.
All config lives in .env (repo root or ~/.lawclaw/.env).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

CONFIG_DIR = Path.home() / ".lawclaw"


def _parse_env_file(path: Path) -> None:
    """Parse a .env file into os.environ (no external deps)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")  # strip quotes
        os.environ.setdefault(key, value)  # don't override existing env
    logger.debug("Loaded .env from {}", path)


def _load_dotenv() -> None:
    """Load .env files. Priority: CWD/.env > ~/.lawclaw/.env."""
    _parse_env_file(Path.cwd() / ".env")       # repo-local .env first
    _parse_env_file(CONFIG_DIR / ".env")        # fallback to home dir


@dataclass
class Config:
    # Secrets
    telegram_token: str = ""
    brave_api_key: str = ""

    # LLM (Claude Max proxy only)
    model: str = "claude-opus-4-local"
    temperature: float = 0.7
    max_tokens: int = 4096

    # Telegram
    telegram_allow_from: list[str] = field(default_factory=list)

    # Agent
    max_iterations: int = 15
    memory_window: int = 40

    # Paths
    workspace: str = str(CONFIG_DIR / "workspace")
    db_path: str = str(CONFIG_DIR / "lawclaw.db")


def load_config() -> Config:
    """Load config from ENV vars / .env files. No config.json needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Load .env first so ENV vars are available
    _load_dotenv()

    # Parse comma-separated allow list
    allow_raw = os.environ.get("TELEGRAM_ALLOW_FROM", "")
    allow_from = [u.strip() for u in allow_raw.split(",") if u.strip()]

    config = Config(
        # Secrets
        telegram_token=os.environ.get("TELEGRAM_TOKEN", ""),
        brave_api_key=os.environ.get("BRAVE_API_KEY", ""),
        # LLM (Claude Max proxy only)
        model=os.environ.get("MODEL", "claude-opus-4-local"),
        temperature=float(os.environ.get("TEMPERATURE", "0.7")),
        max_tokens=int(os.environ.get("MAX_TOKENS", "4096")),
        # Telegram
        telegram_allow_from=allow_from,
        # Agent
        max_iterations=int(os.environ.get("MAX_ITERATIONS", "15")),
        memory_window=int(os.environ.get("MEMORY_WINDOW", "40")),
        # Paths
        workspace=os.environ.get("WORKSPACE", str(CONFIG_DIR / "workspace")),
        db_path=os.environ.get("DB_PATH", str(CONFIG_DIR / "lawclaw.db")),
    )

    return config
