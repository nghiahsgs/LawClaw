"""Judicial branch — pre-check engine and audit logger."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from lawclaw.db import log_audit

if TYPE_CHECKING:
    from lawclaw.core.legislative import LegislativeBranch

DANGEROUS_PATTERNS: list[str] = [
    r"rm\s+-[rf]+\s+/",          # rm -rf /
    r"rm\s+-[rf]+\s+~",          # rm -rf ~
    r"rm\s+--no-preserve-root",
    r"mkfs\.",                    # format disk
    r"dd\s+if=",                  # dd disk copy
    r":\(\)\s*\{.*:\|:&\s*\}",   # fork bomb
    r"DROP\s+TABLE",              # SQL destructive
    r"DROP\s+DATABASE",
    r"TRUNCATE\s+TABLE",
    r"shutdown\s+-[hH]",          # system shutdown
    r"halt\b",
    r"poweroff\b",
    r"reboot\b",
    r"format\s+[A-Za-z]:",        # Windows format
    r"del\s+/[Ss]\s+/[Qq]",      # Windows del /S /Q
    r"chmod\s+-R\s+777\s+/",     # chmod 777 root
    r"chown\s+-R\s+.*\s+/",      # chown root
    r">\s*/dev/sd[a-z]",          # write to raw disk
    r"curl.*\|\s*bash",           # curl pipe bash
    r"wget.*\|\s*bash",
    r"base64\s+-d.*\|\s*bash",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]


@dataclass
class Verdict:
    allowed: bool
    reason: str | None = None


class JudicialBranch:
    def __init__(self, conn: sqlite3.Connection, workspace: str | None = None) -> None:
        self._conn = conn
        self._workspace = Path(workspace).resolve() if workspace else None

    def pre_check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        legislative: LegislativeBranch,
    ) -> Verdict:
        """Run pre-execution checks. Return Verdict(allowed, reason)."""
        # 1. Check legislative approval
        if not legislative.is_approved(tool_name):
            reason = f"Tool '{tool_name}' is not approved by the Legislative branch."
            logger.warning("BLOCKED — {}", reason)
            return Verdict(allowed=False, reason=reason)

        # 2. Check arguments for dangerous patterns
        args_str = json.dumps(arguments)
        for pattern in _COMPILED_PATTERNS:
            if pattern.search(args_str):
                reason = f"Dangerous pattern detected in arguments for '{tool_name}'."
                logger.warning("BLOCKED — {} | pattern: {}", reason, pattern.pattern)
                return Verdict(allowed=False, reason=reason)

        # 3. Check file paths are within workspace (only for exec_cmd)
        if self._workspace is not None and tool_name == "exec_cmd":
            for value in self._flatten_values(arguments):
                if isinstance(value, str) and ("/" in value or "\\" in value):
                    # Skip URLs — they contain / but aren't file paths
                    if value.startswith(("http://", "https://", "ftp://")):
                        continue
                    # Skip long strings (likely prompts/messages, not paths)
                    if len(value) > 500:
                        continue
                    try:
                        candidate = Path(value).resolve()
                        # Only block if it's clearly a path that escapes workspace
                        if candidate.is_absolute():
                            try:
                                candidate.relative_to(self._workspace)
                            except ValueError:
                                reason = (
                                    f"Path '{value[:200]}' is outside the workspace directory."
                                )
                                logger.warning("BLOCKED — {}", reason)
                                return Verdict(allowed=False, reason=reason)
                    except (OSError, ValueError):
                        pass

        return Verdict(allowed=True)

    def log_action(
        self,
        session_key: str | None,
        tool_name: str,
        args: dict[str, Any] | None,
        result: str | None,
        verdict: Verdict,
    ) -> None:
        """Persist an audit entry."""
        log_audit(
            conn=self._conn,
            session_key=session_key,
            tool_name=tool_name,
            arguments=args,
            result=result,
            verdict="allowed" if verdict.allowed else "blocked",
            reason=verdict.reason,
        )

    def get_audit_log(
        self, session_key: str | None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent audit entries for a session (or all if session_key is None)."""
        if session_key is not None:
            rows = self._conn.execute(
                "SELECT * FROM audit_log WHERE session_key = ? ORDER BY id DESC LIMIT ?",
                (session_key, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Helpers --

    @staticmethod
    def _flatten_values(obj: Any) -> list[Any]:
        """Recursively collect all values from a nested dict/list."""
        values: list[Any] = []
        if isinstance(obj, dict):
            for v in obj.values():
                values.extend(JudicialBranch._flatten_values(v))
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                values.extend(JudicialBranch._flatten_values(item))
        else:
            values.append(obj)
        return values
