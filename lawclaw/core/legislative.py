"""Legislative branch — manages skill approval and laws."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from loguru import logger


class LegislativeBranch:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- Skill Approval --

    def is_approved(self, tool_name: str) -> bool:
        """Return True if skill is approved."""
        row = self._conn.execute(
            "SELECT status FROM skills WHERE name = ?", (tool_name,)
        ).fetchone()
        if row is None:
            return False
        return row["status"] == "approved"

    def approve_skill(self, name: str, description: str = "") -> None:
        """Approve a skill by name."""
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO skills (name, status, description, approved_by, approved_at, created_at)
            VALUES (?, 'approved', ?, 'owner', ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                status = 'approved',
                description = excluded.description,
                approved_by = 'owner',
                approved_at = excluded.approved_at
            """,
            (name, description, now, now),
        )
        self._conn.commit()
        logger.info("Skill approved: {}", name)

    def ban_skill(self, name: str) -> None:
        """Ban a skill by name."""
        self._conn.execute(
            """
            INSERT INTO skills (name, status, created_at)
            VALUES (?, 'banned', ?)
            ON CONFLICT(name) DO UPDATE SET status = 'banned'
            """,
            (name, time.time()),
        )
        self._conn.commit()
        logger.warning("Skill banned: {}", name)

    def get_pending(self) -> list[dict[str, Any]]:
        """Return list of skills with pending status."""
        rows = self._conn.execute(
            "SELECT name, description, created_at FROM skills WHERE status = 'pending'"
        ).fetchall()
        return [dict(r) for r in rows]

    def register_builtin(self, tool_names: list[str]) -> None:
        """Auto-approve built-in tools if not already in registry."""
        for name in tool_names:
            existing = self._conn.execute(
                "SELECT status FROM skills WHERE name = ?", (name,)
            ).fetchone()
            if existing is None:
                self.approve_skill(name, description=f"Built-in tool: {name}")
                logger.debug("Auto-approved built-in skill: {}", name)
            elif existing["status"] == "pending":
                self.approve_skill(name, description=f"Built-in tool: {name}")
                logger.debug("Promoted pending skill to approved: {}", name)

    # -- Laws & Constitution --

    def load_laws(self, laws_dir: Path) -> str:
        """Concatenate all .md files in the laws directory."""
        if not laws_dir.exists():
            logger.warning("Laws directory not found: {}", laws_dir)
            return ""
        parts: list[str] = []
        for md_file in sorted(laws_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"## Law: {md_file.stem}\n\n{text}")
            except OSError as exc:
                logger.warning("Could not read law file {}: {}", md_file, exc)
        return "\n\n---\n\n".join(parts)

    def load_constitution(self, path: Path) -> str:
        """Read the constitution file."""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.error("Could not read constitution at {}: {}", path, exc)
            return ""
