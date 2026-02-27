"""Telegram bot integration for LawClaw."""

from __future__ import annotations

import asyncio
import sqlite3

from loguru import logger
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from lawclaw.config import Config
from lawclaw.core.agent import Agent
from lawclaw.core.judicial import JudicialBranch
from lawclaw.core.legislative import LegislativeBranch
from lawclaw.db import clear_session  # kept for potential /purge command


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
        v = self._session_versions.get(chat_id, 0)
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

        self._app = Application.builder().token(self._config.telegram_token).build()

        # Register commands
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(CommandHandler("audit", self._on_audit))
        self._app.add_handler(CommandHandler("skills", self._on_skills))
        self._app.add_handler(CommandHandler("approve", self._on_approve))
        self._app.add_handler(CommandHandler("ban", self._on_ban))
        self._app.add_handler(CommandHandler("jobs", self._on_jobs))
        self._app.add_handler(CommandHandler("help", self._on_help))

        # Message handler
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        # Set bot commands menu
        await self._app.bot.set_my_commands([
            BotCommand("new", "Start new session"),
            BotCommand("audit", "View recent audit log"),
            BotCommand("skills", "List skill statuses"),
            BotCommand("approve", "Approve a pending skill"),
            BotCommand("ban", "Ban a skill"),
            BotCommand("jobs", "List cron jobs"),
            BotCommand("help", "Show commands"),
        ])

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        # Keep running
        while True:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

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
        old_v = self._session_versions.get(chat_id, 0)
        self._session_versions[chat_id] = old_v + 1
        await update.message.reply_text(
            f"🔄 New session started (v{old_v + 1}). Old messages kept in DB."
        )

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
        # Inline import to avoid circular
        from lawclaw.core.cron import CronService
        rows = self._conn.execute(
            "SELECT id, name, schedule_type, schedule_value, enabled, last_status FROM cron_jobs"
        ).fetchall()
        if not rows:
            await update.message.reply_text("No cron jobs.")
            return
        lines = ["⏰ *Cron Jobs:*\n"]
        for r in rows:
            status = "🟢" if r["enabled"] else "⚪"
            lines.append(f"{status} `{r['name']}` ({r['schedule_type']}: {r['schedule_value']})")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
            "/help — Show this message",
            parse_mode="Markdown",
        )

    # -- Message handler --

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._check_access(update):
            return

        text = update.message.text or ""
        if not text.strip():
            return

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
            response = await self._agent.process(message=text, session_key=key, on_progress=_on_progress)
            if response:
                # Telegram has 4096 char limit — split if needed
                for i in range(0, len(response), 4000):
                    chunk = response[i:i + 4000]
                    try:
                        await update.message.reply_text(chunk, parse_mode="Markdown")
                    except Exception:
                        # Fallback to plain text if Markdown parsing fails
                        await update.message.reply_text(chunk)
        except Exception as e:
            logger.error("Error processing message: {}", e)
            await update.message.reply_text(f"⚠️ Error: {str(e)[:200]}")
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
