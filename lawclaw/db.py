"""SQLite database for LawClaw — single source of truth for all persistence."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from loguru import logger

# Default database path
DEFAULT_DB_PATH = Path.home() / ".lawclaw" / "lawclaw.db"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode for concurrent reads."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript("""
        -- Chat sessions and message history
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT NOT NULL,
            role TEXT NOT NULL,  -- 'user', 'assistant', 'system'
            content TEXT NOT NULL,
            tools_used TEXT,     -- JSON array of tool names
            created_at REAL NOT NULL DEFAULT (unixepoch('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_key);

        -- Long-term memory (consolidated from sessions)
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL DEFAULT (unixepoch('now'))
        );

        -- Audit log (Pre-Judicial enforcement)
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT,
            tool_name TEXT NOT NULL,
            arguments TEXT,      -- JSON
            result TEXT,
            verdict TEXT NOT NULL DEFAULT 'allowed',  -- 'allowed', 'blocked', 'flagged'
            reason TEXT,
            created_at REAL NOT NULL DEFAULT (unixepoch('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_key);

        -- Cron jobs
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            message TEXT NOT NULL,       -- Task description for agent
            schedule_type TEXT NOT NULL,  -- 'interval', 'cron', 'once'
            schedule_value TEXT NOT NULL, -- seconds, cron expr, or ISO datetime
            timezone TEXT DEFAULT 'UTC',
            channel TEXT NOT NULL DEFAULT 'telegram',
            chat_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run_at REAL,
            next_run_at REAL,
            last_status TEXT,
            last_error TEXT,
            created_at REAL NOT NULL DEFAULT (unixepoch('now'))
        );

    """)
    conn.commit()
    logger.debug("Database initialized")


# -- Helper functions --

def add_message(conn: sqlite3.Connection, session_key: str, role: str,
                content: str, tools_used: list[str] | None = None) -> None:
    """Insert a message into history."""
    conn.execute(
        "INSERT INTO messages (session_key, role, content, tools_used) VALUES (?, ?, ?, ?)",
        (session_key, role, content, json.dumps(tools_used) if tools_used else None),
    )
    conn.commit()


def get_history(conn: sqlite3.Connection, session_key: str,
                limit: int = 50) -> list[dict[str, Any]]:
    """Get recent message history for a session."""
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_key = ? ORDER BY id DESC LIMIT ?",
        (session_key, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_session(conn: sqlite3.Connection, session_key: str) -> None:
    """Clear all messages for a session."""
    conn.execute("DELETE FROM messages WHERE session_key = ?", (session_key,))
    conn.commit()


def log_audit(conn: sqlite3.Connection, session_key: str | None, tool_name: str,
              arguments: dict | None, result: str | None,
              verdict: str = "allowed", reason: str | None = None) -> None:
    """Log an action to the audit trail."""
    conn.execute(
        "INSERT INTO audit_log (session_key, tool_name, arguments, result, verdict, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_key, tool_name, json.dumps(arguments) if arguments else None,
         result[:2000] if result else None, verdict, reason),
    )
    conn.commit()
