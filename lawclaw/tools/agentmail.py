"""AgentMail tool — manage email inboxes, send/receive emails for the agent."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from lawclaw.core.tools import Tool


class AgentMailTool(Tool):
    name = "agentmail"
    description = (
        "Manage email inboxes and send/receive emails. "
        "Actions: create_inbox, list_inboxes, delete_inbox, "
        "send_message, list_messages, get_message, reply, "
        "list_threads, get_thread."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_inbox",
                    "list_inboxes",
                    "delete_inbox",
                    "send_message",
                    "list_messages",
                    "get_message",
                    "reply",
                    "list_threads",
                    "get_thread",
                ],
                "description": "The action to perform.",
            },
            "inbox_id": {
                "type": "string",
                "description": "Inbox ID (required for most actions except create/list inboxes).",
            },
            "message_id": {
                "type": "string",
                "description": "Message ID (for get_message, reply).",
            },
            "thread_id": {
                "type": "string",
                "description": "Thread ID (for get_thread).",
            },
            "to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Recipient email addresses (for send_message).",
            },
            "subject": {
                "type": "string",
                "description": "Email subject (for send_message).",
            },
            "text": {
                "type": "string",
                "description": "Plain text body (for send_message, reply).",
            },
            "html": {
                "type": "string",
                "description": "HTML body (for send_message, reply). Optional.",
            },
            "username": {
                "type": "string",
                "description": "Username for the inbox email address (for create_inbox).",
            },
            "display_name": {
                "type": "string",
                "description": "Display name for the inbox (for create_inbox).",
            },
        },
        "required": ["action"],
    }

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        action = kwargs.get("action", "")
        logger.debug("agentmail: action={}", action)

        if not self._api_key:
            return "Error: AGENTMAIL_API_KEY is not configured."

        try:
            from agentmail import AgentMail
        except ImportError:
            return "Error: agentmail package not installed. Run: pip install agentmail"

        client = AgentMail(api_key=self._api_key)

        try:
            if action == "create_inbox":
                from agentmail.inboxes.types import CreateInboxRequest
                req = CreateInboxRequest(
                    username=kwargs.get("username"),
                    display_name=kwargs.get("display_name"),
                )
                inbox = client.inboxes.create(request=req)
                return f"Inbox created:\n  Email/ID: {inbox.inbox_id}\n  Display name: {inbox.display_name}"

            elif action == "list_inboxes":
                result = client.inboxes.list()
                inboxes = result.items if hasattr(result, "items") else []
                if not inboxes:
                    return "No inboxes found."
                lines = ["Inboxes:"]
                for ib in inboxes:
                    lines.append(f"  - {ib.inbox_id} (display: {getattr(ib, 'display_name', '')})")
                return "\n".join(lines)

            elif action == "delete_inbox":
                inbox_id = kwargs.get("inbox_id", "")
                if not inbox_id:
                    return "Error: inbox_id is required for delete_inbox."
                client.inboxes.delete(inbox_id)
                return f"Inbox {inbox_id} deleted."

            elif action == "send_message":
                inbox_id = kwargs.get("inbox_id", "")
                to = kwargs.get("to", [])
                subject = kwargs.get("subject", "")
                text = kwargs.get("text", "")
                html = kwargs.get("html")
                if not inbox_id:
                    return "Error: inbox_id is required."
                if not to:
                    return "Error: 'to' recipients are required."
                send_kwargs: dict[str, Any] = {
                    "to": to,
                    "subject": subject,
                    "text": text,
                }
                if html:
                    send_kwargs["html"] = html
                result = client.inboxes.messages.send(inbox_id, **send_kwargs)
                return f"Message sent!\n  Message ID: {result.message_id}\n  Thread ID: {result.thread_id}"

            elif action == "list_messages":
                inbox_id = kwargs.get("inbox_id", "")
                if not inbox_id:
                    return "Error: inbox_id is required."
                result = client.inboxes.messages.list(inbox_id)
                msgs = result.items if hasattr(result, "items") else []
                if not msgs:
                    return "No messages found."
                lines = ["Messages:"]
                for m in msgs:
                    frm = getattr(m, "from_", None) or getattr(m, "from", "unknown")
                    if hasattr(frm, "email"):
                        frm = frm.email
                    mid = getattr(m, "message_id", getattr(m, "id", "?"))
                    lines.append(f"  - [{mid}] From: {frm} | Subject: {getattr(m, 'subject', '(no subject)')}")
                return "\n".join(lines)

            elif action == "get_message":
                inbox_id = kwargs.get("inbox_id", "")
                message_id = kwargs.get("message_id", "")
                if not inbox_id or not message_id:
                    return "Error: inbox_id and message_id are required."
                m = client.inboxes.messages.get(inbox_id, message_id)
                frm = getattr(m, "from_", None) or getattr(m, "from", "unknown")
                if hasattr(frm, "email"):
                    frm = frm.email
                mid = getattr(m, "message_id", getattr(m, "id", "?"))
                return (
                    f"Message {mid}:\n"
                    f"  From: {frm}\n"
                    f"  Subject: {getattr(m, 'subject', '')}\n"
                    f"  Date: {getattr(m, 'created_at', '')}\n"
                    f"  Body:\n{getattr(m, 'text', '(no text)')}"
                )

            elif action == "reply":
                inbox_id = kwargs.get("inbox_id", "")
                message_id = kwargs.get("message_id", "")
                text = kwargs.get("text", "")
                if not inbox_id or not message_id or not text:
                    return "Error: inbox_id, message_id, and text are required."
                reply_kwargs: dict[str, Any] = {"text": text}
                html = kwargs.get("html")
                if html:
                    reply_kwargs["html"] = html
                result = client.inboxes.messages.reply(inbox_id, message_id, **reply_kwargs)
                return f"Reply sent! Message ID: {result.message_id}"

            elif action == "list_threads":
                inbox_id = kwargs.get("inbox_id", "")
                if not inbox_id:
                    return "Error: inbox_id is required."
                result = client.inboxes.threads.list(inbox_id)
                threads = result.items if hasattr(result, "items") else []
                if not threads:
                    return "No threads found."
                lines = ["Threads:"]
                for t in threads:
                    tid = getattr(t, "thread_id", getattr(t, "id", "?"))
                    lines.append(f"  - [{tid}] Subject: {getattr(t, 'subject', '(no subject)')} | Messages: {getattr(t, 'message_count', '?')}")
                return "\n".join(lines)

            elif action == "get_thread":
                inbox_id = kwargs.get("inbox_id", "")
                thread_id = kwargs.get("thread_id", "")
                if not inbox_id or not thread_id:
                    return "Error: inbox_id and thread_id are required."
                t = client.inboxes.threads.get(inbox_id, thread_id)
                tid = getattr(t, "thread_id", getattr(t, "id", "?"))
                lines = [f"Thread {tid} — Subject: {getattr(t, 'subject', '')}"]
                messages = getattr(t, "messages", [])
                for m in messages:
                    frm = getattr(m, "from_", None) or getattr(m, "from", "unknown")
                    if hasattr(frm, "email"):
                        frm = frm.email
                    mid = getattr(m, "message_id", getattr(m, "id", "?"))
                    lines.append(f"  [{mid}] From: {frm}: {getattr(m, 'text', '')[:200]}")
                return "\n".join(lines)

            else:
                return f"Unknown action: {action}"

        except Exception as exc:
            logger.exception("agentmail tool error")
            return f"AgentMail error: {exc}"
