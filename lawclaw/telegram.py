"""Telegram bot integration for LawClaw."""

from __future__ import annotations

import asyncio
import base64
import re
import sqlite3

from loguru import logger


def _convert_tables(text: str) -> str:
    """Convert markdown tables to monospace code blocks for Telegram."""
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        if lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
            # Collect all consecutive table lines
            table_lines: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                table_lines.append(lines[i])
                i += 1
            result.append(_render_table(table_lines))
        else:
            result.append(lines[i])
            i += 1

    return "\n".join(result)


def _render_table(table_lines: list[str]) -> str:
    """Render markdown table lines as ASCII table inside a code block."""
    rows: list[list[str]] = []
    for line in table_lines:
        stripped = line.strip()
        # Skip separator rows like |---|---|
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return "\n".join(table_lines)

    num_cols = max(len(r) for r in rows)
    widths = [0] * num_cols
    for row in rows:
        for j, cell in enumerate(row[:num_cols]):
            widths[j] = max(widths[j], len(cell))

    top    = "┌─" + "─┬─".join("─" * w for w in widths) + "─┐"
    sep    = "├─" + "─┼─".join("─" * w for w in widths) + "─┤"
    bottom = "└─" + "─┴─".join("─" * w for w in widths) + "─┘"

    formatted: list[str] = [top]
    for idx, row in enumerate(rows):
        cells = [row[j].ljust(widths[j]) if j < len(row) else " " * widths[j] for j in range(num_cols)]
        formatted.append("│ " + " │ ".join(cells) + " │")
        if idx == 0 and len(rows) > 1:
            formatted.append(sep)
    formatted.append(bottom)

    return "```\n" + "\n".join(formatted) + "\n```"
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

from lawclaw.config import Config
from lawclaw.core.agent import Agent
from lawclaw.core.judicial import JudicialBranch
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.db import clear_session, get_max_session_version


class TelegramBot:
    """Telegram bot that wraps the LawClaw agent."""

    def __init__(
        self,
        config: Config,
        agent: Agent,
        conn: sqlite3.Connection,
        legislative: LegislativeBranch,
        judicial: JudicialBranch,
    ) -> None:
        self._config = config
        self._agent = agent
        self._conn = conn
        self._legislative = legislative
        self._judicial = judicial
        self._app: Application | None = None
        self._session_versions: dict[int, int] = {}  # chat_id → version counter

    def _session_key(self, chat_id: int) -> str:
        if chat_id not in self._session_versions:
            # Restore from DB + bump so restart = fresh session
            db_version = get_max_session_version(self._conn, chat_id)
            self._session_versions[chat_id] = db_version + 1
        v = self._session_versions[chat_id]
        return f"telegram:{chat_id}:v{v}"

    def _is_allowed(self, user_id: int) -> bool:
        if not self._config.telegram_allow_from:
            return True  # Empty list = allow all
        return str(user_id) in self._config.telegram_allow_from

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self._config.telegram_token:
            logger.error("Telegram token not configured")
            return

        proxy = self._config.telegram_proxy or None
        if proxy:
            logger.info("Telegram using proxy: {}", proxy)

        builder = Application.builder().token(self._config.telegram_token)
        if proxy:
            builder = builder.request(
                HTTPXRequest(proxy=proxy, read_timeout=120, write_timeout=120, connect_timeout=30, pool_timeout=30)
            ).get_updates_request(
                HTTPXRequest(proxy=proxy, read_timeout=120, connect_timeout=30, pool_timeout=30)
            )
        else:
            builder = builder.read_timeout(120).write_timeout(120).connect_timeout(30).pool_timeout(30)
        self._app = builder.build()

        # Register commands
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(CommandHandler("audit", self._on_audit))
        self._app.add_handler(CommandHandler("skills", self._on_skills))
        self._app.add_handler(CommandHandler("approve", self._on_approve))
        self._app.add_handler(CommandHandler("ban", self._on_ban))
        self._app.add_handler(CommandHandler("jobs", self._on_jobs))
        self._app.add_handler(CommandHandler("memory", self._on_memory))
        self._app.add_handler(CommandHandler("models", self._on_models))
        self._app.add_handler(CommandHandler("help", self._on_help))

        # Message handlers
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._on_photo))

        # Set bot commands menu (non-critical — don't let it crash startup)
        try:
            await self._app.bot.set_my_commands([
                BotCommand("new", "Start new session"),
                BotCommand("audit", "View recent audit log"),
                BotCommand("skills", "List skill statuses"),
                BotCommand("approve", "Approve a pending skill"),
                BotCommand("ban", "Ban a skill"),
                BotCommand("jobs", "List cron jobs"),
                BotCommand("models", "Switch LLM model"),
                BotCommand("help", "Show commands"),
            ])
        except Exception as exc:
            logger.warning("Failed to set bot commands (non-critical): {}", exc)

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        # Keep running
        while True:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        if self._app:
            try:
                if self._app.updater and self._app.updater.running:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as exc:
                logger.warning("Error during bot shutdown: {}", exc)

    # -- Command handlers --

    async def _on_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        await update.message.reply_text(
            "🏛️ *LawClaw* — The Governed AI Agent\n\n"
            "I operate under a constitution with separation of powers.\n"
            "Every action is audited. Type /help for commands.",
            parse_mode="Markdown",
        )

    async def _on_new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        chat_id = update.effective_chat.id
        # Clear old session messages so they never leak back
        old_key = self._session_key(chat_id)
        clear_session(self._conn, old_key)
        # Bump version
        old_v = self._session_versions[chat_id]
        self._session_versions[chat_id] = old_v + 1
        await update.message.reply_text("🔄 New session started. Old messages cleared.")

    async def _on_audit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        import datetime

        # /audit → current session only, /audit all → all entries
        args = (update.message.text or "").split()
        show_all = len(args) > 1 and args[1].lower() == "all"

        if show_all:
            entries = self._judicial.get_audit_log(None, limit=15)
        else:
            key = self._session_key(update.effective_chat.id)
            entries = self._judicial.get_audit_log(key, limit=15)

        if not entries:
            await update.message.reply_text("No audit entries yet.")
            return

        scope = "All Sessions" if show_all else "Current Session"
        lines = [f"📋 *Audit Log ({scope}):*\n"]

        for e in entries:
            icon = "✅" if e["verdict"] == "allowed" else "⛔"

            # Parse caller context from session_key
            sk = e.get("session_key") or "unknown"
            if sk.startswith("telegram:"):
                caller = "👤 user"
            elif sk.startswith("cron:"):
                parts = sk.split(":")
                caller = f"⏰ cron:{parts[1]}" if len(parts) >= 2 else "⏰ cron"
            elif sk.startswith("subagent:"):
                caller = "🤖 subagent"
            else:
                caller = sk[:20]

            # Format timestamp
            ts = e.get("created_at")
            time_str = ""
            if ts:
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                time_str = dt.strftime("%H:%M:%S")

            # Arguments preview (truncated)
            args_preview = ""
            if e.get("arguments"):
                raw = e["arguments"]
                # Truncate long args
                if len(raw) > 80:
                    raw = raw[:77] + "..."
                args_preview = f"\n   📎 `{raw}`"

            lines.append(f"{icon} `{e['tool_name']}` — {e['verdict']}  [{caller} {time_str}]{args_preview}")
            if e.get("reason"):
                lines.append(f"   ⚠️ {e['reason']}")

        lines.append(f"\n_Tip: /audit all — show all sessions_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _on_skills(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        tool_names = self._agent._tools.list_names()
        blocked = self._judicial.get_blocked_tools()
        if not tool_names:
            await update.message.reply_text("No skills available.")
            return
        lines = ["🧠 *AI Skills:*\n"]
        for name in sorted(tool_names):
            if name in blocked:
                lines.append(f"🚫 `{name}` — blocked by Pre-Judicial")
            else:
                lines.append(f"✅ `{name}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _on_approve(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        args = update.message.text.split(maxsplit=1)
        if len(args) < 2:
            await update.message.reply_text("Usage: /approve tool_name")
            return
        tool_name = args[1].strip()
        self._judicial.approve_tool(tool_name)
        await update.message.reply_text(f"✅ `{tool_name}` unblocked by Pre-Judicial.", parse_mode="Markdown")

    async def _on_ban(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        args = update.message.text.split(maxsplit=1)
        if len(args) < 2:
            await update.message.reply_text("Usage: /ban tool_name")
            return
        tool_name = args[1].strip()
        self._judicial.ban_tool(tool_name)
        await update.message.reply_text(f"🚫 `{tool_name}` blocked by Pre-Judicial.", parse_mode="Markdown")

    async def _on_jobs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        import datetime
        from lawclaw.db import get_cron_history

        args = (update.message.text or "").split(maxsplit=1)

        # /jobs <name> → show detail for a specific job
        if len(args) >= 2:
            search = args[1].strip()
            row = self._conn.execute(
                "SELECT id, name, message, schedule_type, schedule_value, enabled, last_status, last_error, last_run_at, created_at FROM cron_jobs WHERE name = ? OR id = ?",
                (search, search),
            ).fetchone()
            if not row:
                # Fuzzy match
                row = self._conn.execute(
                    "SELECT id, name, message, schedule_type, schedule_value, enabled, last_status, last_error, last_run_at, created_at FROM cron_jobs WHERE name LIKE ?",
                    (f"%{search}%",),
                ).fetchone()
            if not row:
                await update.message.reply_text(f"Job not found: {search}")
                return

            status = "🟢 Enabled" if row["enabled"] else "⚪ Disabled"
            created = ""
            if row["created_at"]:
                dt = datetime.datetime.fromtimestamp(row["created_at"], tz=datetime.timezone.utc)
                created = dt.strftime("%Y-%m-%d %H:%M UTC")
            last_run = "Never"
            if row["last_run_at"]:
                dt = datetime.datetime.fromtimestamp(row["last_run_at"], tz=datetime.timezone.utc)
                last_run = dt.strftime("%Y-%m-%d %H:%M UTC")

            # Full prompt (no truncation)
            prompt = row["message"].replace("`", "\\`")

            lines = [
                f"⏰ *Job Detail:* `{row['name']}`\n",
                f"*Status:* {status}",
                f"*Schedule:* {row['schedule_type']}: {row['schedule_value']}",
                f"*Created:* {created}",
                f"*Last run:* {last_run}",
                f"*Last status:* {row['last_status'] or 'N/A'}",
            ]
            if row["last_error"]:
                err = row["last_error"][:200].replace("`", "\\`")
                lines.append(f"*Last error:* {err}")

            lines.append(f"\n*Prompt:*\n```\n{prompt}\n```")

            # Recent runs
            runs = get_cron_history(self._conn, row["id"], limit=5)
            if runs:
                lines.append("\n*Recent runs:*")
                for run in runs:
                    run_time = run["run_at"] if run["run_at"] else "?"
                    run_icon = "✅" if run["status"] == "ok" else "❌"
                    summary = (run["summary"] or "")[:100].replace("`", "\\`")
                    lines.append(f"{run_icon} {run_time} — {summary}...")

            text = "\n".join(lines)
            for i in range(0, len(text), 4000):
                chunk = text[i:i + 4000]
                try:
                    await update.message.reply_text(chunk, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(chunk)
            return

        # /jobs → list all jobs
        rows = self._conn.execute(
            "SELECT id, name, message, schedule_type, schedule_value, enabled, last_status, last_run_at FROM cron_jobs"
        ).fetchall()
        if not rows:
            await update.message.reply_text("No cron jobs.")
            return
        lines = ["⏰ *Cron Jobs:*\n"]
        for r in rows:
            status = "🟢" if r["enabled"] else "⚪"
            last_run = ""
            if r["last_run_at"]:
                dt = datetime.datetime.fromtimestamp(r["last_run_at"], tz=datetime.timezone.utc)
                last_run = f" | last: {dt.strftime('%m/%d %H:%M')}"
            last_status = f" | {r['last_status']}" if r["last_status"] else ""
            prompt = r["message"][:80] + "..." if len(r["message"]) > 80 else r["message"]
            prompt = prompt.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")
            lines.append(
                f"{status} `{r['name']}`\n"
                f"   ⏱ {r['schedule_type']}: {r['schedule_value']}{last_run}{last_status}\n"
                f"   📝 {prompt}"
            )
        lines.append("\n_Tip: /jobs <name> — view full detail_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _on_memory(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        rows = self._conn.execute(
            "SELECT key, value, updated_at FROM memory ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        if not rows:
            await update.message.reply_text("No memory entries.")
            return
        lines = ["🧠 *Memory:*\n"]
        for r in rows:
            key = r["key"]
            val = r["value"]
            # Mask sensitive values (API keys, tokens)
            if any(kw in key.lower() for kw in ("key", "token", "secret", "password")):
                val = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
            elif len(val) > 100:
                val = val[:100] + "..."
            lines.append(f"• `{key}`\n  {val}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _on_models(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        args = (update.message.text or "").split()

        # Preset model options grouped by provider
        presets = {
            "claude-proxy": [
                "claude-opus-4",
                "claude-sonnet-4",
                "claude-haiku-4",
            ],
            "openrouter": [
                "google/gemini-2.5-flash",
                "google/gemini-2.5-pro",
                "anthropic/claude-sonnet-4",
                "anthropic/claude-haiku-4",
                "deepseek/deepseek-chat-v3-0324",
                "meta-llama/llama-4-maverick",
            ],
            "alibaba": [
                "qwen3-max",
                "qwen3.5-plus",
                "qwen3.5-flash",
                "qwen-plus",
                "qwen-turbo",
                "qwen-max",
                "qwen3-coder-plus",
            ],
        }

        llm = self._agent._llm

        # /models → show current + options
        if len(args) < 2:
            lines = [
                f"🤖 *Current model:*",
                f"  Provider: `{llm.provider}`",
                f"  Model: `{llm.model}`\n",
                "*Available presets:*\n",
            ]
            idx = 1
            for provider, models in presets.items():
                has_key = (
                    provider == "claude-proxy"  # no key needed
                    or (provider == "openrouter" and self._config.openrouter_api_key)
                    or (provider == "alibaba" and self._config.alibaba_api_key)
                )
                key_status = "✅" if has_key else "🔑 no key"
                lines.append(f"*{provider}* ({key_status}):")
                for m in models:
                    marker = "→ " if m == llm.model and provider == llm.provider else "  "
                    lines.append(f"{marker}`{idx}` {m}")
                    idx += 1
                lines.append("")
            lines.append("_Usage: /models <number>_")
            lines.append("_Or: /models <provider> <model>_")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        # /models <number> → pick from preset list
        if len(args) == 2 and args[1].isdigit():
            num = int(args[1])
            flat: list[tuple[str, str]] = []
            for provider, models in presets.items():
                for m in models:
                    flat.append((provider, m))
            if num < 1 or num > len(flat):
                await update.message.reply_text(f"Invalid number. Choose 1-{len(flat)}.")
                return
            provider, model = flat[num - 1]
            try:
                llm.switch(provider, model)
                await update.message.reply_text(
                    f"✅ Switched to `{provider}` / `{model}`",
                    parse_mode="Markdown",
                )
            except ValueError as e:
                await update.message.reply_text(f"❌ {e}")
            return

        # /models <provider> <model> → custom
        if len(args) >= 3:
            provider = args[1]
            model = args[2]
            try:
                llm.switch(provider, model)
                await update.message.reply_text(
                    f"✅ Switched to `{provider}` / `{model}`",
                    parse_mode="Markdown",
                )
            except ValueError as e:
                await update.message.reply_text(f"❌ {e}")
            return

        await update.message.reply_text("Usage: /models or /models <number> or /models <provider> <model>")

    async def _on_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        await update.message.reply_text(
            "🏛️ *LawClaw Commands:*\n\n"
            "/new — Start new session\n"
            "/audit — View recent audit log\n"
            "/skills — List skill statuses\n"
            "/approve name — Approve a skill\n"
            "/ban name — Ban a skill\n"
            "/jobs — List cron jobs\n"
            "/memory — View stored memory\n"
            "/models — Switch LLM model\n"
            "/help — Show this message",
            parse_mode="Markdown",
        )

    # -- Message handlers --

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        text = update.message.text or ""
        if not text.strip():
            return
        await self._handle_message(update, text)

    async def _on_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return
        caption = update.message.caption or "What's in this image?"
        # Download the highest resolution photo
        photo = update.message.photo[-1]  # last = largest
        try:
            file = await photo.get_file()
            img_bytes = await file.download_as_bytearray()
            b64 = base64.b64encode(bytes(img_bytes)).decode()
            # Detect mime type from file path
            ext = (file.file_path or "").rsplit(".", 1)[-1].lower()
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")
            image_url = f"data:{mime};base64,{b64}"
            logger.info("Photo received: {}KB, mime={}", len(img_bytes) // 1024, mime)
        except Exception as e:
            logger.error("Failed to download photo: {}", e)
            await update.message.reply_text("⚠️ Failed to download image.")
            return
        await self._handle_message(update, caption, images=[image_url])

    async def _handle_message(
        self, update: Update, text: str, images: list[str] | None = None,
    ) -> None:
        chat_id = update.effective_chat.id
        key = self._session_key(chat_id)

        # Keep typing indicator alive every 4s while agent processes
        typing_active = True

        async def _keep_typing() -> None:
            while typing_active:
                try:
                    await update.effective_chat.send_action("typing")
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(_keep_typing())

        # Progress callback — sends brief status to Telegram on each tool execution
        status_msg = None  # Reuse a single message to avoid spam

        def _on_progress(tool_name: str, args_preview: str, result_preview: str) -> None:
            nonlocal status_msg
            icons = {
                "web_search": "🔍", "web_fetch": "🌐", "exec_cmd": "⚙️",
                "manage_memory": "💾", "manage_cron": "⏰", "spawn_subagent": "🤖",
                "chrome": "🌐",
            }
            icon = icons.get(tool_name, "🔧")
            # Truncate args for display
            short_args = args_preview[:80].replace("\n", " ")
            text_msg = f"{icon} `{tool_name}` {short_args}..."

            async def _send() -> None:
                nonlocal status_msg
                try:
                    if status_msg:
                        await status_msg.edit_text(text_msg, parse_mode="Markdown")
                    else:
                        status_msg = await update.message.reply_text(text_msg, parse_mode="Markdown")
                except Exception:
                    pass  # Telegram rate limit or parse error — skip

            asyncio.create_task(_send())

        try:
            # Global timeout: if agent hangs (stuck tool), abort after 20 minutes
            # so the bot stays responsive for other messages
            try:
                response = await asyncio.wait_for(
                    self._agent.process(
                        message=text, session_key=key,
                        on_progress=_on_progress, images=images,
                    ),
                    timeout=1200.0,
                )
            except asyncio.TimeoutError:
                logger.error("Agent process timed out after 1200s for session {}", key)
                await update.message.reply_text(
                    "⚠️ Request timed out after 20 minutes. Please try a simpler request."
                )
                return

            # Send queued file attachments before text response
            sf_tool = self._agent._tools.get("send_file")
            if sf_tool and hasattr(sf_tool, "collect"):
                for att in sf_tool.collect():
                    try:
                        with open(att["path"], "rb") as f:
                            if att.get("kind") == "photo":
                                await update.message.reply_photo(photo=f, caption=att.get("caption") or None)
                            else:
                                await update.message.reply_document(document=f, caption=att.get("caption") or None)
                    except Exception as e:
                        logger.error("Failed to send attachment: {}", e)
                        await update.message.reply_text(f"⚠️ Failed to send file: {att.get('path', '?')}")

            if response:
                # Convert markdown tables to ASCII code blocks (Telegram doesn't support tables)
                response = _convert_tables(response)
                # Telegram has 4096 char limit — split if needed
                for i in range(0, len(response), 4000):
                    chunk = response[i:i + 4000]
                    try:
                        await update.message.reply_text(chunk, parse_mode="Markdown")
                    except Exception:
                        # Fallback to plain text if Markdown parsing fails
                        await update.message.reply_text(chunk)
        except Exception as e:
            logger.error("Error processing message: {}", e, exc_info=True)
            err_msg = str(e).strip() or type(e).__name__
            await update.message.reply_text(f"⚠️ Error: {err_msg[:200]}")
        finally:
            typing_active = False
            typing_task.cancel()
            # Clean up progress status message
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

    def _check_access(self, update: Update) -> bool:
        user_id = update.effective_user.id if update.effective_user else None
        if user_id and not self._is_allowed(user_id):
            logger.warning("Access denied for user {}", user_id)
            return False
        return True
