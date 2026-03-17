"""LSP (Language Server Protocol) tool — code intelligence for the AI agent.

Provides go-to-definition, find-references, hover (type info), and diagnostics
by communicating with language servers via JSON-RPC over stdin/stdout.

Supported language servers (auto-detected):
  - Python: pyright (npm install -g pyright)
  - TypeScript/JavaScript: typescript-language-server (npm install -g typescript-language-server)
  - Go: gopls (go install golang.org/x/tools/gopls@latest)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

from loguru import logger

from lawclaw.core.tools import Tool

# Map file extensions to language server commands and language IDs
_LANG_SERVERS: dict[str, dict[str, Any]] = {
    ".py": {
        "cmd": ["pyright-langserver", "--stdio"],
        "fallback_cmd": ["pyright", "--stdio"],
        "language_id": "python",
    },
    ".ts": {
        "cmd": ["typescript-language-server", "--stdio"],
        "language_id": "typescript",
    },
    ".tsx": {
        "cmd": ["typescript-language-server", "--stdio"],
        "language_id": "typescriptreact",
    },
    ".js": {
        "cmd": ["typescript-language-server", "--stdio"],
        "language_id": "javascript",
    },
    ".jsx": {
        "cmd": ["typescript-language-server", "--stdio"],
        "language_id": "javascriptreact",
    },
    ".go": {
        "cmd": ["gopls", "serve"],
        "language_id": "go",
    },
}


def _file_uri(path: Path) -> str:
    """Convert a file path to a file:// URI."""
    return f"file://{url_quote(str(path.resolve()), safe='/:@')}"


class _LspClient:
    """Minimal LSP client that communicates via JSON-RPC over stdin/stdout."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._initialized = False
        self._root_uri: str = ""

    async def start(self, cmd: list[str], workspace: Path) -> None:
        """Start the language server process."""
        self._root_uri = _file_uri(workspace)

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace),
        )
        self._reader_task = asyncio.create_task(self._read_loop())

        # Send initialize request
        result = await self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": self._root_uri,
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                },
            },
        })

        # Send initialized notification
        await self._notify("initialized", {})
        self._initialized = True
        logger.info("LSP server initialized: {}", cmd[0])
        return result

    async def stop(self) -> None:
        """Shutdown the language server."""
        if not self._proc:
            return
        try:
            await self._request("shutdown", None)
            await self._notify("exit", None)
        except Exception:
            pass
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc:
            self._proc.kill()
            await self._proc.wait()
        self._proc = None
        self._initialized = False

    async def open_file(self, path: Path, language_id: str) -> None:
        """Notify the server that a file is opened."""
        text = path.read_text(encoding="utf-8", errors="replace")
        await self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": _file_uri(path),
                "languageId": language_id,
                "version": 1,
                "text": text,
            },
        })

    async def definition(self, path: Path, line: int, character: int) -> Any:
        """Go to definition at position (0-based line/char)."""
        return await self._request("textDocument/definition", {
            "textDocument": {"uri": _file_uri(path)},
            "position": {"line": line, "character": character},
        })

    async def references(self, path: Path, line: int, character: int) -> Any:
        """Find all references at position (0-based line/char)."""
        return await self._request("textDocument/references", {
            "textDocument": {"uri": _file_uri(path)},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })

    async def hover(self, path: Path, line: int, character: int) -> Any:
        """Get hover info (type, docs) at position (0-based line/char)."""
        return await self._request("textDocument/hover", {
            "textDocument": {"uri": _file_uri(path)},
            "position": {"line": line, "character": character},
        })

    # --- JSON-RPC transport ---

    async def _request(self, method: str, params: Any) -> Any:
        """Send a JSON-RPC request and wait for response."""
        self._request_id += 1
        rid = self._request_id

        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = future
        await self._send(msg)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise TimeoutError(f"LSP request '{method}' timed out after 30s")

        return result

    async def _notify(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._send(msg)

    async def _send(self, msg: dict) -> None:
        """Send a JSON-RPC message with Content-Length header."""
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("LSP server not running")
        body = json.dumps(msg)
        header = f"Content-Length: {len(body.encode())}\r\n\r\n"
        self._proc.stdin.write(header.encode() + body.encode())
        await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from the server's stdout."""
        if not self._proc or not self._proc.stdout:
            return
        reader = self._proc.stdout
        try:
            while True:
                # Read headers
                content_length = 0
                while True:
                    line = await reader.readline()
                    if not line:
                        return  # EOF
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        break  # End of headers
                    if line_str.startswith("Content-Length:"):
                        content_length = int(line_str.split(":")[1].strip())

                if content_length == 0:
                    continue

                # Read body
                body = await reader.readexactly(content_length)
                msg = json.loads(body.decode("utf-8"))

                # Handle response
                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(RuntimeError(
                            f"LSP error: {msg['error'].get('message', msg['error'])}"
                        ))
                    else:
                        future.set_result(msg.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("LSP reader loop error: {}", exc)


class LspTool(Tool):
    """Code intelligence via Language Server Protocol."""

    name = "lsp"
    description = (
        "Code intelligence — understand code structure using Language Server Protocol. "
        "Actions: 'definition' (go to definition), 'references' (find all usages), "
        "'hover' (get type info and docs). "
        "Much more accurate than grep for understanding code. "
        "Line numbers are 1-based (same as read_file output)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["definition", "references", "hover"],
                "description": (
                    "What to do: "
                    "'definition' = jump to where symbol is defined, "
                    "'references' = find all places symbol is used, "
                    "'hover' = get type signature and documentation."
                ),
            },
            "file": {
                "type": "string",
                "description": "File path (relative to workspace).",
            },
            "line": {
                "type": "integer",
                "description": "Line number (1-based, as shown by read_file).",
            },
            "character": {
                "type": "integer",
                "description": "Column/character position (0-based) of the symbol.",
            },
        },
        "required": ["action", "file", "line", "character"],
    }

    def __init__(self, workspace: str) -> None:
        self._workspace = Path(workspace).resolve()
        # Cache active LSP clients by language server command
        self._clients: dict[str, _LspClient] = {}

    async def execute(  # type: ignore[override]
        self,
        action: str,
        file: str,
        line: int,
        character: int = 0,
    ) -> str:
        # Resolve file path
        fpath = Path(file)
        if not fpath.is_absolute():
            fpath = self._workspace / fpath
        fpath = fpath.resolve()

        if not fpath.exists():
            return f"Error: file not found — {fpath}"

        # Find language server for this file type
        ext = fpath.suffix.lower()
        server_config = _LANG_SERVERS.get(ext)
        if not server_config:
            return f"Error: no language server configured for '{ext}' files. Supported: {', '.join(_LANG_SERVERS.keys())}"

        # Check if language server binary exists
        cmd = server_config["cmd"]
        binary = cmd[0]
        if not shutil.which(binary):
            # Try fallback command if available
            fallback = server_config.get("fallback_cmd")
            if fallback and shutil.which(fallback[0]):
                cmd = fallback
                binary = cmd[0]
            else:
                install_hints = {
                    "pyright-langserver": "npm install -g pyright",
                    "pyright": "npm install -g pyright",
                    "typescript-language-server": "npm install -g typescript-language-server",
                    "gopls": "go install golang.org/x/tools/gopls@latest",
                }
                hint = install_hints.get(binary, f"install {binary}")
                return f"Error: language server '{binary}' not found. Install with: {hint}"

        logger.info("lsp: action={} file={} line={} char={}", action, fpath, line, character)

        # Get or create LSP client
        client_key = binary
        client = self._clients.get(client_key)
        if not client or not client._initialized:
            client = _LspClient()
            try:
                await client.start(cmd, self._workspace)
            except Exception as exc:
                return f"Error starting language server '{binary}': {exc}"
            self._clients[client_key] = client

        # Open file in LSP
        language_id = server_config["language_id"]
        try:
            await client.open_file(fpath, language_id)
        except Exception as exc:
            return f"Error opening file in LSP: {exc}"

        # Small delay to let server analyze the file
        await asyncio.sleep(0.5)

        # Convert 1-based line to 0-based (LSP uses 0-based)
        lsp_line = max(0, line - 1)

        try:
            if action == "definition":
                result = await client.definition(fpath, lsp_line, character)
                return self._format_locations(result, "Definition")

            elif action == "references":
                result = await client.references(fpath, lsp_line, character)
                return self._format_locations(result, "References")

            elif action == "hover":
                result = await client.hover(fpath, lsp_line, character)
                return self._format_hover(result)

            else:
                return f"Error: unknown action '{action}'. Use: definition, references, hover"

        except TimeoutError as exc:
            return str(exc)
        except Exception as exc:
            return f"Error executing LSP {action}: {exc}"

    def _format_locations(self, result: Any, label: str) -> str:
        """Format location results from definition/references."""
        if not result:
            return f"No {label.lower()} found."

        # Normalize to list
        locations = result if isinstance(result, list) else [result]

        lines = [f"{label} ({len(locations)} result{'s' if len(locations) > 1 else ''}):"]
        for loc in locations[:50]:  # Cap at 50
            uri = loc.get("uri", loc.get("targetUri", ""))
            rng = loc.get("range", loc.get("targetRange", {}))
            start = rng.get("start", {})
            line_num = start.get("line", 0) + 1  # Convert back to 1-based

            # Convert URI to relative path
            path = uri.replace("file://", "")
            try:
                path = str(Path(path).relative_to(self._workspace))
            except ValueError:
                pass

            # Try to read the actual line for context
            context = ""
            try:
                full_path = self._workspace / path if not Path(path).is_absolute() else Path(path)
                if full_path.exists():
                    file_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    if 0 <= line_num - 1 < len(file_lines):
                        context = f"  →  {file_lines[line_num - 1].strip()}"
            except Exception:
                pass

            lines.append(f"  {path}:{line_num}{context}")

        return "\n".join(lines)

    def _format_hover(self, result: Any) -> str:
        """Format hover result (type info + docs)."""
        if not result:
            return "No hover info available."

        contents = result.get("contents", "")

        # contents can be string, MarkedString, or MarkupContent
        if isinstance(contents, str):
            return contents
        elif isinstance(contents, dict):
            value = contents.get("value", "")
            return value
        elif isinstance(contents, list):
            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", ""))
            return "\n---\n".join(parts)

        return str(contents)
