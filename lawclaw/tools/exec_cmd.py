"""Shell command execution tool with timeout and workspace restriction."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool


class ExecCmdTool(Tool):
    name = "exec_cmd"
    description = (
        "Execute a shell command and return stdout + stderr. "
        "Commands run inside the configured workspace directory."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 1800).",
                "default": 30,
            },
        },
        "required": ["command"],
    }

    def __init__(self, workspace: str | None = None) -> None:
        self._workspace = Path(workspace).resolve() if workspace else None

    async def execute(self, command: str, timeout: int = 30) -> str:  # type: ignore[override]
        timeout = max(1, min(timeout, 1800))
        cwd = str(self._workspace) if self._workspace else None

        logger.info("exec_cmd: command='{}' timeout={} cwd={}", command[:100], timeout, cwd)

        env = {**os.environ}
        # Strip sensitive vars
        for key in ("BRAVE_API_KEY", "TELEGRAM_TOKEN"):
            env.pop(key, None)

        try:
            # start_new_session=True creates a new process group so we can
            # kill the entire tree (including background children like `npm run dev &`)
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout)
                )
            except asyncio.TimeoutError:
                # Kill the entire process group, not just the shell
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                # Secondary timeout on post-kill cleanup to avoid hanging forever
                try:
                    await asyncio.wait_for(proc.communicate(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    pass
                return f"Command timed out after {timeout}s: {command}"

            stdout = stdout_bytes.decode(errors="replace").rstrip()
            stderr = stderr_bytes.decode(errors="replace").rstrip()
            returncode = proc.returncode

            parts: list[str] = [f"Exit code: {returncode}"]
            if stdout:
                parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                parts.append(f"STDERR:\n{stderr}")
            if not stdout and not stderr:
                parts.append("(no output)")

            return "\n\n".join(parts)

        except PermissionError as exc:
            return f"Permission denied: {exc}"
        except OSError as exc:
            return f"OS error executing command: {exc}"
