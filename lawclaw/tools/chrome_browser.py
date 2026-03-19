"""Chrome browser automation tool with multi-profile support.

Uses Puppeteer's bundled Chromium via Node.js scripts.
Profiles stored at ~/.lawclaw/workspace/chrome/profiles/{name}/.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool
from lawclaw.tools.send_file import SendFileTool

# Directory containing Node.js scripts (relative to this file)
SCRIPTS_DIR = Path(__file__).parent.parent / "chrome" / "scripts"
CHROME_DIR = Path.home() / ".lawclaw" / "workspace" / "chrome"


class ChromeBrowserTool(Tool):
    name = "chrome"
    description = (
        "Control a Chrome browser with persistent profiles. "
        "Profiles persist login sessions across restarts. "
        "Actions: start_profile, stop_profile, list_profiles, delete_profile, "
        "navigate, screenshot, click, fill, evaluate, page_info."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "start_profile", "stop_profile", "list_profiles",
                    "delete_profile", "navigate", "screenshot",
                    "click", "fill", "evaluate", "page_info",
                ],
                "description": "Browser action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Profile name (for start/stop/delete_profile).",
            },
            "headless": {
                "type": "boolean",
                "description": "Run headless (default false). Set true for background automation.",
            },
            "url": {
                "type": "string",
                "description": "URL (for navigate, or initial URL when starting profile).",
            },
            "selector": {
                "type": "string",
                "description": "CSS or XPath selector (for click, fill, screenshot element).",
            },
            "value": {
                "type": "string",
                "description": "Text value (for fill).",
            },
            "script": {
                "type": "string",
                "description": "JavaScript to execute (for evaluate).",
            },
            "output": {
                "type": "string",
                "description": "Output file path (for screenshot).",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page screenshot (default false).",
            },
        },
        "required": ["action"],
    }

    def __init__(self, workspace: str = "") -> None:
        self._workspace = Path(workspace) if workspace else None
        self._node_path = "node"
        self._deps_checked = False
        self._send_file: SendFileTool | None = None

    def set_send_file(self, sf: SendFileTool) -> None:
        """Link send_file tool so screenshots auto-queue for delivery."""
        self._send_file = sf

    async def execute(  # type: ignore[override]
        self,
        action: str,
        name: str = "",
        headless: bool = False,
        url: str = "",
        selector: str = "",
        value: str = "",
        script: str = "",
        output: str = "",
        full_page: bool = False,
    ) -> str:
        try:
            if not self._deps_checked:
                await self._ensure_deps()
                self._deps_checked = True

            return await self._dispatch(
                action=action, name=name, headless=headless,
                url=url, selector=selector, value=value,
                script=script, output=output, full_page=full_page,
            )
        except Exception as exc:
            logger.exception("Chrome browser error")
            return f"Error: {exc}"

    async def _ensure_deps(self) -> None:
        """Check node_modules exists, install if not."""
        node_modules = SCRIPTS_DIR / "node_modules"
        if not node_modules.exists():
            logger.info("Installing Chrome scripts dependencies...")
            proc = await asyncio.create_subprocess_exec(
                "npm", "install", "--production",
                cwd=str(SCRIPTS_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(
                    f"npm install failed: {stderr.decode()}"
                )
            logger.info("Chrome scripts dependencies installed")

    async def _run_script(
        self, script_name: str, args: list[str], timeout: float = 120.0,
        detach: bool = False,
    ) -> dict[str, Any]:
        """Run a Node.js script and return parsed JSON output."""
        script_path = SCRIPTS_DIR / script_name
        cmd = [self._node_path, str(script_path)] + args

        if detach:
            # For launch-profile: start in background, read first line of output
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(SCRIPTS_DIR),
            )
            try:
                # Read first line (JSON output before keep-alive)
                line = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=30.0
                )
                output = line.decode().strip()
                if output:
                    return json.loads(output)
                return {"success": False, "error": "No output from script"}
            except asyncio.TimeoutError:
                proc.kill()
                return {"success": False, "error": "Timeout waiting for browser launch"}

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(SCRIPTS_DIR),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "error": f"Script timed out after {timeout}s"}

        out = stdout.decode().strip()
        err = stderr.decode().strip()

        # Try stdout first, then stderr for error JSON
        for text in [out, err]:
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue

        if proc.returncode != 0:
            return {"success": False, "error": err or out or f"Exit code {proc.returncode}"}
        return {"success": True, "message": out or "OK"}

    async def _ensure_browser(self, name: str = "default", headless: bool = False) -> str | None:
        """Ensure a browser profile is running. Auto-start if needed, auto-swap if different."""
        # Check if any browser is running
        endpoint_file = CHROME_DIR / ".browser-endpoint"
        meta_file = CHROME_DIR / ".profile-meta"

        if endpoint_file.exists():
            try:
                import json as _json
                if meta_file.exists():
                    meta = _json.loads(meta_file.read_text())
                    if meta.get("profileName") == name:
                        return None  # same profile, already running
                # Different profile running — stop it first
                await self._run_script("close-persistent.js", [])
            except Exception:
                # Stale endpoint, clean up
                try:
                    endpoint_file.unlink(missing_ok=True)
                except Exception:
                    pass

        # Start the requested profile
        args = ["--name", name]
        if headless:
            args.extend(["--headless", "true"])
        else:
            args.append("--no-headless")
        result = await self._run_script("launch-profile.js", args, detach=True)
        if result.get("success"):
            return f"Auto-started profile '{name}'."
        return f"[ERROR] Failed to start profile '{name}': {result.get('error', 'unknown')}"

    async def _dispatch(
        self, *, action: str, name: str, headless: bool, url: str,
        selector: str, value: str, script: str, output: str, full_page: bool,
    ) -> str:
        # -- profile management --

        if action == "start_profile":
            if not name:
                return "[ERROR] 'name' is required for start_profile."
            # Auto-stop different running profile before starting new one
            startup_msg = await self._ensure_browser(name=name, headless=headless)
            if startup_msg and startup_msg.startswith("[ERROR]"):
                return startup_msg
            if url:
                await self._run_script("navigate.js", ["--url", url])
            return startup_msg or f"Profile '{name}' already running."

        if action == "stop_profile":
            result = await self._run_script("close-persistent.js", [])
            return self._format(result)

        if action == "list_profiles":
            result = await self._run_script("launch-profile.js", ["--list"])
            return self._format(result)

        if action == "delete_profile":
            if not name:
                return "[ERROR] 'name' is required for delete_profile."
            profile_dir = CHROME_DIR / "profiles" / name
            if not profile_dir.exists():
                return f"Profile '{name}' not found."
            import shutil
            shutil.rmtree(profile_dir, ignore_errors=True)
            return f"Profile '{name}' deleted."

        # -- browser interaction (requires running profile) --

        # Check if a browser is running, hint LLM to list_profiles + start_profile first
        endpoint_file = CHROME_DIR / ".browser-endpoint"
        if not endpoint_file.exists():
            return (
                "[ERROR] No browser running. "
                "Call chrome(action='list_profiles') first to see available profiles, "
                "then chrome(action='start_profile', name='...') to start one."
            )

        if action == "navigate":
            if not url:
                return "[ERROR] 'url' is required for navigate."
            result = await self._run_script("navigate.js", ["--url", url])
            return self._format(result)

        if action == "screenshot":
            if not output:
                # Auto-generate output path
                import time
                ws = self._workspace or CHROME_DIR
                ws.mkdir(parents=True, exist_ok=True)
                output = str(ws / f"screenshot_{int(time.time())}.png")
            args = ["--output", output]
            if selector:
                args.extend(["--selector", selector])
            if full_page:
                args.extend(["--full-page", "true"])
            result = await self._run_script("screenshot.js", args)
            if result.get("success"):
                saved_path = result.get("output", output)
                # Auto-queue for sending to user
                if self._send_file:
                    await self._send_file.execute(path=saved_path)
                    return (
                        f"Screenshot saved and queued for sending: {saved_path}\n"
                        f"Size: {result.get('size', 'unknown')} bytes"
                    )
                return (
                    f"Screenshot saved: {saved_path}\n"
                    f"Size: {result.get('size', 'unknown')} bytes\n"
                    f"Use send_file to deliver it to the user."
                )
            return self._format(result)

        if action == "click":
            if not selector:
                return "[ERROR] 'selector' is required for click."
            args = ["--selector", selector]
            if url:
                args.extend(["--url", url])
            result = await self._run_script("click.js", args)
            return self._format(result)

        if action == "fill":
            if not selector:
                return "[ERROR] 'selector' is required for fill."
            if not value:
                return "[ERROR] 'value' is required for fill."
            result = await self._run_script("fill.js", [
                "--selector", selector, "--value", value,
            ])
            return self._format(result)

        if action == "evaluate":
            if not script:
                return "[ERROR] 'script' is required for evaluate."
            result = await self._run_script("evaluate.js", ["--script", script])
            return self._format(result)

        if action == "page_info":
            result = await self._run_script("evaluate.js", [
                "--script", "({url: document.location.href, title: document.title})",
            ])
            if result.get("success"):
                info = result.get("result", {})
                return f"URL: {info.get('url', 'unknown')}\nTitle: {info.get('title', 'unknown')}"
            return self._format(result)

        return f"Unknown action: {action}"

    def _format(self, result: dict[str, Any]) -> str:
        """Format script result for LLM consumption."""
        if result.get("success"):
            parts = []
            for key in ["message", "url", "title", "result", "profiles", "active"]:
                if key in result:
                    val = result[key]
                    if isinstance(val, (dict, list)):
                        parts.append(f"{key}: {json.dumps(val, indent=2)}")
                    else:
                        parts.append(f"{key}: {val}")
            return "\n".join(parts) if parts else "OK"
        return f"Error: {result.get('error', 'Unknown error')}"
