"""Chrome DevTools Protocol browser control tool.

Controls a Chrome browser via CDP WebSocket. Chrome must be running
with --remote-debugging-port (default 9222).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from loguru import logger

try:
    import websockets  # type: ignore[import-untyped]

    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False
    logger.debug("websockets not installed; chrome tool unavailable")

from lawclaw.core.tools import Tool


# ---------------------------------------------------------------------------
# Internal CDP WebSocket client
# ---------------------------------------------------------------------------


class CdpClient:
    """Persistent WebSocket connection to Chrome's CDP endpoint."""

    def __init__(self, port: int = 9222, timeout: float = 30.0) -> None:
        self._port = port
        self._timeout = timeout
        self._ws: Any = None
        self._msg_id: int = 0

    # -- connection management --

    async def _ensure_connected(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.ping()
                return
            except Exception:
                self._ws = None

        # Connect to a page/tab WebSocket (not browser-level)
        # because Page.*, Runtime.*, Input.* only work on tab targets.
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://localhost:{self._port}/json")
            resp.raise_for_status()
            targets = resp.json()

        # Find first "page" type target
        ws_url = None
        for target in targets:
            if target.get("type") == "page":
                ws_url = target.get("webSocketDebuggerUrl")
                break

        if not ws_url:
            raise ConnectionError(
                "No page target found. Make sure Chrome has at least one tab open."
            )

        self._ws = await websockets.connect(  # type: ignore[attr-defined]
            ws_url,
            max_size=50 * 1024 * 1024,  # 50 MB for screenshots
        )
        logger.info("CDP connected to {}", ws_url)

    async def _send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_connected()
        self._msg_id += 1
        mid = self._msg_id
        payload: dict[str, Any] = {"id": mid, "method": method}
        if params:
            payload["params"] = params

        await self._ws.send(json.dumps(payload))

        deadline = asyncio.get_event_loop().time() + self._timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"CDP command '{method}' timed out after {self._timeout}s")
            raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            resp = json.loads(raw)
            if resp.get("id") == mid:
                if "error" in resp:
                    err = resp["error"]
                    raise RuntimeError(f"CDP error: {err.get('message', err)}")
                return resp.get("result", {})
            # skip CDP events

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None

    # -- high-level CDP commands --

    async def navigate(self, url: str) -> dict[str, Any]:
        return await self._send("Page.navigate", {"url": url})

    async def go_back(self) -> dict[str, Any]:
        return await self._send("Page.goBack")

    async def go_forward(self) -> dict[str, Any]:
        return await self._send("Page.goForward")

    async def reload(self) -> dict[str, Any]:
        return await self._send("Page.reload")

    async def evaluate(self, expression: str) -> Any:
        result = await self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        obj = result.get("result", {})
        if obj.get("type") == "undefined":
            return None
        if "value" in obj:
            return obj["value"]
        if obj.get("subtype") == "error":
            desc = result.get("exceptionDetails", {}).get("text", obj.get("description", "JS error"))
            raise RuntimeError(f"JS error: {desc}")
        return obj.get("description", str(obj))

    async def screenshot(self) -> str:
        result = await self._send("Page.captureScreenshot", {"format": "png"})
        return result.get("data", "")

    async def page_info(self) -> dict[str, str]:
        url = await self.evaluate("document.location.href")
        title = await self.evaluate("document.title")
        return {"url": str(url or ""), "title": str(title or "")}

    async def list_tabs(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://localhost:{self._port}/json")
            resp.raise_for_status()
            return resp.json()

    async def new_tab(self, url: str = "about:blank") -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            target = f"http://localhost:{self._port}/json/new"
            if url and url != "about:blank":
                target += f"?{url}"
            resp = await client.get(target)
            resp.raise_for_status()
            return resp.json()

    async def close_tab(self, target_id: str) -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://localhost:{self._port}/json/close/{target_id}")
            return resp.text

    async def dispatch_key(self, key: str) -> None:
        for event_type in ("keyDown", "keyUp"):
            await self._send("Input.dispatchKeyEvent", {
                "type": event_type,
                "key": key,
                "code": key,
            })


# ---------------------------------------------------------------------------
# LawClaw Tool
# ---------------------------------------------------------------------------


class ChromeCdpTool(Tool):
    name = "chrome"
    description = (
        "Control a Chrome browser via CDP. "
        "Chrome must be running with --remote-debugging-port. "
        "Actions: navigate, click, type, get_content, screenshot, scroll, "
        "evaluate, go_back, go_forward, reload, wait_for, page_info, "
        "list_tabs, new_tab, close_tab, press_key."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate", "click", "type", "get_content", "screenshot",
                    "scroll", "evaluate", "go_back", "go_forward", "reload",
                    "wait_for", "page_info", "list_tabs", "new_tab",
                    "close_tab", "press_key",
                ],
                "description": "Browser action to perform.",
            },
            "url": {
                "type": "string",
                "description": "URL (for 'navigate', 'new_tab').",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector (for 'click', 'type', 'wait_for', 'scroll').",
            },
            "text": {
                "type": "string",
                "description": "Text to type (for 'type').",
            },
            "expression": {
                "type": "string",
                "description": "JavaScript expression (for 'evaluate').",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "Scroll direction (default 'down').",
            },
            "amount": {
                "type": "integer",
                "description": "Scroll pixels (default 500).",
            },
            "key": {
                "type": "string",
                "description": "Key name for 'press_key' (e.g. 'Enter', 'Tab').",
            },
            "target_id": {
                "type": "string",
                "description": "Tab target ID (for 'close_tab').",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout seconds for wait_for (default 10, max 30).",
            },
            "max_chars": {
                "type": "integer",
                "description": "Max characters for get_content (default 50000).",
            },
        },
        "required": ["action"],
    }

    def __init__(self, port: int = 9222) -> None:
        self._cdp = CdpClient(port=port)

    async def execute(  # type: ignore[override]
        self,
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
        expression: str = "",
        direction: str = "down",
        amount: int = 500,
        key: str = "",
        target_id: str = "",
        timeout: int = 10,
        max_chars: int = 50000,
    ) -> str:
        if not _HAS_WEBSOCKETS:
            return "Error: 'websockets' package not installed. Run: pip install websockets"

        try:
            return await self._dispatch(
                action=action, url=url, selector=selector, text=text,
                expression=expression, direction=direction, amount=amount,
                key=key, target_id=target_id, timeout=timeout,
                max_chars=max_chars,
            )
        except ConnectionError as exc:
            return (
                f"Error: Cannot connect to Chrome CDP. "
                f"Make sure Chrome is running with --remote-debugging-port. "
                f"Details: {exc}"
            )
        except TimeoutError as exc:
            return f"Error: CDP command timed out. {exc}"
        except RuntimeError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.exception("Chrome CDP error")
            return f"Error executing chrome '{action}': {exc}"

    async def _dispatch(  # noqa: C901
        self,
        *,
        action: str,
        url: str,
        selector: str,
        text: str,
        expression: str,
        direction: str,
        amount: int,
        key: str,
        target_id: str,
        timeout: int,
        max_chars: int,
    ) -> str:
        cdp = self._cdp

        # -- navigation --

        if action == "navigate":
            if not url:
                return "[ERROR] 'url' is required for 'navigate'."
            await cdp.navigate(url)
            await asyncio.sleep(0.5)
            info = await cdp.page_info()
            return f"Navigated to: {info['url']}\nTitle: {info['title']}"

        if action == "go_back":
            await cdp.go_back()
            await asyncio.sleep(0.5)
            info = await cdp.page_info()
            return f"Went back to: {info['url']}\nTitle: {info['title']}"

        if action == "go_forward":
            await cdp.go_forward()
            await asyncio.sleep(0.5)
            info = await cdp.page_info()
            return f"Went forward to: {info['url']}\nTitle: {info['title']}"

        if action == "reload":
            await cdp.reload()
            await asyncio.sleep(1.0)
            info = await cdp.page_info()
            return f"Reloaded: {info['url']}\nTitle: {info['title']}"

        # -- interaction --

        if action == "click":
            if not selector:
                return "[ERROR] 'selector' is required for 'click'."
            sel = _escape_js(selector)
            result = await cdp.evaluate(
                f"(() => {{"
                f"  const el = document.querySelector('{sel}');"
                f"  if (!el) return 'Element not found: {sel}';"
                f"  el.scrollIntoView({{block:'center'}});"
                f"  el.click();"
                f"  return 'Clicked: {sel}';"
                f"}})()"
            )
            return str(result)

        if action == "type":
            if not selector:
                return "[ERROR] 'selector' is required for 'type'."
            if not text:
                return "[ERROR] 'text' is required for 'type'."
            sel = _escape_js(selector)
            txt = _escape_js(text)
            result = await cdp.evaluate(
                f"(() => {{"
                f"  const el = document.querySelector('{sel}');"
                f"  if (!el) return 'Element not found: {sel}';"
                f"  el.focus();"
                f"  el.value = '{txt}';"
                f"  el.dispatchEvent(new Event('input', {{bubbles:true}}));"
                f"  el.dispatchEvent(new Event('change', {{bubbles:true}}));"
                f"  return 'Typed into: {sel}';"
                f"}})()"
            )
            return str(result)

        if action == "press_key":
            if not key:
                return "[ERROR] 'key' is required for 'press_key'."
            await cdp.dispatch_key(key)
            return f"Pressed key: {key}"

        if action == "scroll":
            px = -amount if direction == "up" else amount
            if selector:
                sel = _escape_js(selector)
                result = await cdp.evaluate(
                    f"(() => {{"
                    f"  const el = document.querySelector('{sel}');"
                    f"  if (!el) return 'Element not found: {sel}';"
                    f"  el.scrollBy(0, {px});"
                    f"  return 'Scrolled element by {px}px';"
                    f"}})()"
                )
                return str(result)
            await cdp.evaluate(f"window.scrollBy(0, {px})")
            return f"Scrolled page by {px}px"

        # -- inspection --

        if action == "get_content":
            max_c = max(100, min(max_chars, 200_000))
            content = str(await cdp.evaluate("document.body.innerText") or "")
            info = await cdp.page_info()
            if len(content) > max_c:
                content = content[:max_c] + f"\n\n[Truncated — showed {max_c} of {len(content)} chars]"
            return f"Page: {info['url']}\nTitle: {info['title']}\n\n{content}"

        if action == "screenshot":
            b64 = await cdp.screenshot()
            if not b64:
                return "Error: Screenshot returned empty data."
            return f"[SCREENSHOT:base64png]{b64}"

        if action == "evaluate":
            if not expression:
                return "[ERROR] 'expression' is required for 'evaluate'."
            result = await cdp.evaluate(expression)
            return f"Result: {json.dumps(result, default=str)[:50000]}"

        if action == "page_info":
            info = await cdp.page_info()
            return f"URL: {info['url']}\nTitle: {info['title']}"

        if action == "wait_for":
            if not selector:
                return "[ERROR] 'selector' is required for 'wait_for'."
            wait_s = max(1, min(timeout, 30))
            sel = _escape_js(selector)
            elapsed = 0.0
            while elapsed < wait_s:
                found = await cdp.evaluate(f"document.querySelector('{sel}') !== null")
                if found:
                    return f"Element found: {selector} (after {elapsed:.1f}s)"
                await asyncio.sleep(0.5)
                elapsed += 0.5
            return f"Timeout: '{selector}' not found after {wait_s}s"

        # -- tab management --

        if action == "list_tabs":
            tabs = await cdp.list_tabs()
            if not tabs:
                return "No tabs open."
            lines = []
            for i, t in enumerate(tabs, 1):
                lines.append(
                    f"{i}. {t.get('title', 'Untitled')}\n"
                    f"   URL: {t.get('url', '')}\n"
                    f"   ID: {t.get('id', '')}"
                )
            return "Open tabs:\n\n" + "\n\n".join(lines)

        if action == "new_tab":
            tab = await cdp.new_tab(url or "about:blank")
            return f"New tab created:\n  ID: {tab.get('id', '')}\n  URL: {tab.get('url', '')}"

        if action == "close_tab":
            if not target_id:
                return "[ERROR] 'target_id' is required for 'close_tab'."
            result = await cdp.close_tab(target_id)
            return f"Tab closed: {result}"

        return f"Unknown action: {action}"


def _escape_js(s: str) -> str:
    """Escape a string for safe embedding in a JS single-quoted literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
