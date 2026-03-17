"""Git operations tool — structured git actions for the AI agent.

Provides status, diff, log, commit, and branch operations with
clean structured output instead of raw command output.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool


async def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    env = {**os.environ}
    # Prevent git from opening interactive editors
    env["GIT_EDITOR"] = "true"
    env["GIT_TERMINAL_PROMPT"] = "0"

    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=float(timeout)
        )
    except asyncio.TimeoutError:
        proc.kill()
        return 1, "", f"git {args[0]} timed out after {timeout}s"

    return (
        proc.returncode or 0,
        stdout_bytes.decode(errors="replace").rstrip(),
        stderr_bytes.decode(errors="replace").rstrip(),
    )


class GitTool(Tool):
    """Structured git operations for code management."""

    name = "git"
    description = (
        "Git operations with structured output. "
        "Actions: 'status' (working tree state), 'diff' (show changes), "
        "'log' (recent commits), 'commit' (stage and commit files), "
        "'branch' (list/create/switch branches). "
        "Prefer this over exec_cmd for git operations."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "diff", "log", "commit", "branch"],
                "description": (
                    "'status' = show modified/untracked files, "
                    "'diff' = show file changes (staged + unstaged), "
                    "'log' = show recent commits, "
                    "'commit' = stage files and commit with message, "
                    "'branch' = list, create, or switch branches."
                ),
            },
            "path": {
                "type": "string",
                "description": "Repository path relative to workspace (default: current repo in workspace).",
                "default": ".",
            },
            "message": {
                "type": "string",
                "description": "Commit message (required for 'commit' action).",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files to stage for commit. Use ['.'] for all changes. Default: all modified files.",
            },
            "branch_name": {
                "type": "string",
                "description": "Branch name for 'branch' action (create or switch to).",
            },
            "count": {
                "type": "integer",
                "description": "Number of commits to show for 'log' (default: 10).",
                "default": 10,
            },
        },
        "required": ["action"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()

    def _resolve_repo(self, path: str) -> str:
        """Resolve repo path within workspace."""
        repo = self._workspace / path
        return str(repo.resolve())

    async def execute(  # type: ignore[override]
        self,
        action: str,
        path: str = ".",
        message: str = "",
        files: list[str] | None = None,
        branch_name: str = "",
        count: int = 10,
    ) -> str:
        cwd = self._resolve_repo(path)
        logger.info("git: action={} cwd={}", action, cwd)

        if action == "status":
            return await self._status(cwd)
        elif action == "diff":
            return await self._diff(cwd)
        elif action == "log":
            return await self._log(cwd, count)
        elif action == "commit":
            if not message:
                return "Error: 'message' is required for commit action."
            return await self._commit(cwd, message, files)
        elif action == "branch":
            return await self._branch(cwd, branch_name)
        else:
            return f"Error: unknown action '{action}'."

    async def _status(self, cwd: str) -> str:
        """Show working tree status in a clean format."""
        # Get branch info
        rc, branch, _ = await _run_git(["branch", "--show-current"], cwd)
        branch_name = branch.strip() or "(detached)"

        # Get status
        rc, out, err = await _run_git(["status", "--porcelain=v1"], cwd)
        if rc != 0:
            return f"Error: {err}"

        if not out:
            return f"Branch: {branch_name}\nClean — no changes."

        # Parse porcelain output
        staged = []
        unstaged = []
        untracked = []
        for line in out.splitlines():
            if len(line) < 4:
                continue
            index_status = line[0]
            work_status = line[1]
            fname = line[3:]

            if index_status == "?":
                untracked.append(fname)
            else:
                if index_status != " ":
                    staged.append(f"  {index_status} {fname}")
                if work_status != " ":
                    unstaged.append(f"  {work_status} {fname}")

        parts = [f"Branch: {branch_name}"]
        if staged:
            parts.append(f"\nStaged ({len(staged)}):")
            parts.extend(staged)
        if unstaged:
            parts.append(f"\nUnstaged ({len(unstaged)}):")
            parts.extend(unstaged)
        if untracked:
            parts.append(f"\nUntracked ({len(untracked)}):")
            parts.extend(f"  ? {f}" for f in untracked)

        return "\n".join(parts)

    async def _diff(self, cwd: str) -> str:
        """Show diff for both staged and unstaged changes."""
        # Unstaged changes
        rc1, unstaged, _ = await _run_git(["diff", "--stat"], cwd)
        rc2, unstaged_full, _ = await _run_git(["diff"], cwd)

        # Staged changes
        rc3, staged, _ = await _run_git(["diff", "--cached", "--stat"], cwd)
        rc4, staged_full, _ = await _run_git(["diff", "--cached"], cwd)

        parts = []
        if staged:
            parts.append("=== Staged changes ===")
            parts.append(staged)
            if staged_full:
                parts.append(staged_full[:3000])  # Cap output
        if unstaged:
            parts.append("=== Unstaged changes ===")
            parts.append(unstaged)
            if unstaged_full:
                parts.append(unstaged_full[:3000])

        if not parts:
            return "No changes to show."

        result = "\n\n".join(parts)
        if len(result) > 6000:
            result = result[:6000] + "\n\n... (output truncated, use read_file to see specific files)"
        return result

    async def _log(self, cwd: str, count: int) -> str:
        """Show recent commits in clean format."""
        count = max(1, min(count, 50))
        rc, out, err = await _run_git(
            ["log", f"-{count}", "--format=%h %an (%ar) %s"],
            cwd,
        )
        if rc != 0:
            return f"Error: {err}"
        if not out:
            return "No commits yet."
        return f"Recent commits ({count}):\n{out}"

    async def _commit(self, cwd: str, message: str, files: list[str] | None) -> str:
        """Stage files and commit."""
        # Stage files
        if files:
            for f in files:
                rc, _, err = await _run_git(["add", f], cwd)
                if rc != 0:
                    return f"Error staging '{f}': {err}"
        else:
            # Stage all modified/deleted (not untracked)
            rc, _, err = await _run_git(["add", "-u"], cwd)
            if rc != 0:
                return f"Error staging files: {err}"

        # Check if there's anything to commit
        rc, status, _ = await _run_git(["status", "--porcelain=v1"], cwd)
        staged_files = [l for l in status.splitlines() if l and l[0] != " " and l[0] != "?"]
        if not staged_files:
            return "Nothing to commit — no staged changes."

        # Commit
        rc, out, err = await _run_git(["commit", "-m", message], cwd)
        if rc != 0:
            return f"Error committing: {err}"

        # Return summary
        rc, hash_out, _ = await _run_git(["log", "-1", "--format=%h %s"], cwd)
        return f"Committed: {hash_out}\nFiles: {len(staged_files)} changed"

    async def _branch(self, cwd: str, branch_name: str) -> str:
        """List, create, or switch branches."""
        if not branch_name:
            # List branches
            rc, out, err = await _run_git(["branch", "-a", "--format=%(refname:short) %(HEAD)"], cwd)
            if rc != 0:
                return f"Error: {err}"
            # Mark current branch
            lines = []
            for line in out.splitlines():
                parts = line.rsplit(" ", 1)
                name = parts[0]
                is_current = len(parts) > 1 and parts[1] == "*"
                prefix = "→ " if is_current else "  "
                lines.append(f"{prefix}{name}")
            return "Branches:\n" + "\n".join(lines)

        # Check if branch exists
        rc, _, _ = await _run_git(["rev-parse", "--verify", branch_name], cwd)
        if rc == 0:
            # Branch exists — switch to it
            rc, out, err = await _run_git(["checkout", branch_name], cwd)
            if rc != 0:
                return f"Error switching to '{branch_name}': {err}"
            return f"Switched to branch '{branch_name}'"
        else:
            # Create new branch
            rc, out, err = await _run_git(["checkout", "-b", branch_name], cwd)
            if rc != 0:
                return f"Error creating branch '{branch_name}': {err}"
            return f"Created and switched to new branch '{branch_name}'"
