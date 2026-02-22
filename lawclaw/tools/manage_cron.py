"""Cron job management tool — lets the LLM create/remove/list scheduled tasks."""

from __future__ import annotations

from typing import Any

from lawclaw.core.tools import Tool


class ManageCronTool(Tool):
    name = "manage_cron"
    description = (
        "Manage scheduled cron jobs. Actions: "
        "'add' to create a recurring job (specify name, message/prompt to run, interval_seconds), "
        "'remove' to delete a job by ID, "
        "'list' to show all jobs."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "list"],
                "description": "Action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Job name (required for 'add').",
            },
            "message": {
                "type": "string",
                "description": "The prompt/task the agent will execute each interval (required for 'add').",
            },
            "interval_seconds": {
                "type": "integer",
                "description": "Run every N seconds. Minimum 60 (required for 'add').",
            },
            "job_id": {
                "type": "string",
                "description": "Job ID to remove (required for 'remove').",
            },
        },
        "required": ["action"],
    }

    def __init__(self) -> None:
        self._cron: Any = None
        self._chat_id: str = ""

    def set_cron(self, cron: Any) -> None:
        self._cron = cron

    def set_chat_id(self, chat_id: str) -> None:
        self._chat_id = chat_id

    async def execute(  # type: ignore[override]
        self,
        action: str,
        name: str = "",
        message: str = "",
        interval_seconds: int = 0,
        job_id: str = "",
    ) -> str:
        if not self._cron:
            return "[ERROR] CronService not configured."

        if action == "list":
            jobs = self._cron.list_jobs()
            if not jobs:
                return "No cron jobs."
            lines = []
            for j in jobs:
                status = j.get("last_status", "pending")
                lines.append(f"- {j['name']} (ID: {j['id']}) every {j['schedule_value']}s [{status}]")
            return "\n".join(lines)

        elif action == "add":
            if not name or not message:
                return "[ERROR] 'name' and 'message' are required for 'add'."
            interval = max(60, interval_seconds)  # enforce minimum 60s
            job_id = self._cron.add_job(
                name=name,
                message=message,
                chat_id=self._chat_id,
                schedule_type="interval",
                schedule_value=str(interval),
            )
            return f"Cron job created: '{name}' (ID: {job_id}), runs every {interval}s."

        elif action == "remove":
            if not job_id:
                return "[ERROR] 'job_id' is required for 'remove'."
            if self._cron.remove_job(job_id):
                return f"Cron job {job_id} removed."
            return f"Job {job_id} not found."

        return f"Unknown action: {action}"
