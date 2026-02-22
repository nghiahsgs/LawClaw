"""Cron job management tool — lets the LLM create/remove/list scheduled tasks."""

from __future__ import annotations

from typing import Any

from lawclaw.core.tools import Tool


class ManageCronTool(Tool):
    name = "manage_cron"
    description = (
        "Manage scheduled cron jobs. Actions: "
        "'add' to create a recurring job (specify name, message/prompt to run, interval_seconds), "
        "'remove' to delete a job by name or ID (provide either 'name' or 'job_id'), "
        "'update' to change a job's interval (provide name or job_id + interval_seconds), "
        "'list' to show all jobs."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "update", "list"],
                "description": "Action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Job name (required for 'add', can also be used for 'remove').",
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
                "description": "Job ID to remove (optional for 'remove' — can use 'name' instead).",
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
            if job_id:
                if self._cron.remove_job(job_id):
                    return f"Cron job {job_id} removed."
                return f"Job {job_id} not found."
            elif name:
                count = self._cron.remove_job_by_name(name)
                if count > 0:
                    return f"Removed {count} cron job(s) named '{name}'."
                return f"No cron job named '{name}' found."
            else:
                return "[ERROR] Provide 'job_id' or 'name' for 'remove'."

        elif action == "update":
            if not interval_seconds:
                return "[ERROR] 'interval_seconds' is required for 'update'."
            interval = max(60, interval_seconds)
            updated = self._cron.update_job(name=name, job_id=job_id, interval=interval)
            if updated:
                return f"Cron job updated: interval changed to {interval}s."
            return f"Job not found (name='{name}', id='{job_id}')."

        return f"Unknown action: {action}"
