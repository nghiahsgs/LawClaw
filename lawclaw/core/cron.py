"""Cron scheduler — periodic task execution via SQLite."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from typing import Any, Callable, Coroutine

from loguru import logger


class CronService:
    """Simple cron service backed by SQLite."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        on_job: Callable[[str, str, str], Coroutine[Any, Any, str | None]] | None = None,
    ) -> None:
        """
        Args:
            conn: SQLite connection.
            on_job: async callback(job_id, message, chat_id) → optional response string.
        """
        self._conn = conn
        self.on_job = on_job
        self._running = False
        self._task: asyncio.Task | None = None
        self._executing: set[str] = set()

    def start(self) -> None:
        """Start the cron tick loop."""
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info("Cron service started")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Cron service stopped")

    async def _tick_loop(self) -> None:
        """Check for due jobs every 10 seconds."""
        while self._running:
            try:
                await self._check_due_jobs()
            except Exception as e:
                logger.error("Cron tick error: {}", e)
            await asyncio.sleep(10)

    async def _check_due_jobs(self) -> None:
        now = time.time()
        rows = self._conn.execute(
            "SELECT id, name, message, chat_id, schedule_type, schedule_value "
            "FROM cron_jobs WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?",
            (now,),
        ).fetchall()

        for row in rows:
            job_id = row["id"]
            if job_id in self._executing:
                continue
            self._executing.add(job_id)
            asyncio.create_task(self._execute_job(
                job_id, row["name"], row["message"], row["chat_id"],
                row["schedule_type"], row["schedule_value"],
            ))

    async def _execute_job(
        self, job_id: str, name: str, message: str, chat_id: str,
        schedule_type: str, schedule_value: str,
    ) -> None:
        logger.info("Cron: executing '{}' ({})", name, job_id)
        try:
            if self.on_job:
                await self.on_job(job_id, message, chat_id)
            self._conn.execute(
                "UPDATE cron_jobs SET last_run_at = ?, last_status = 'ok', last_error = NULL WHERE id = ?",
                (time.time(), job_id),
            )
        except Exception as e:
            logger.error("Cron job '{}' failed: {}", name, e)
            self._conn.execute(
                "UPDATE cron_jobs SET last_run_at = ?, last_status = 'error', last_error = ? WHERE id = ?",
                (time.time(), str(e), job_id),
            )
        finally:
            self._executing.discard(job_id)

        # Compute next run
        if schedule_type == "once":
            self._conn.execute("UPDATE cron_jobs SET enabled = 0 WHERE id = ?", (job_id,))
        elif schedule_type == "interval":
            interval = float(schedule_value)
            next_run = time.time() + interval
            self._conn.execute("UPDATE cron_jobs SET next_run_at = ? WHERE id = ?", (next_run, job_id))
        self._conn.commit()

    # -- Public API --

    def add_job(
        self, name: str, message: str, chat_id: str,
        schedule_type: str = "interval", schedule_value: str = "3600",
    ) -> str:
        """Add a cron job. Returns job ID."""
        job_id = uuid.uuid4().hex[:12]
        now = time.time()

        if schedule_type == "interval":
            next_run = now + float(schedule_value)
        else:
            next_run = now + 60  # Default: run in 1 minute

        self._conn.execute(
            "INSERT INTO cron_jobs (id, name, message, chat_id, schedule_type, schedule_value, next_run_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, name, message, chat_id, schedule_type, schedule_value, next_run),
        )
        self._conn.commit()
        logger.info("Cron job added: '{}' ({}) every {}s", name, job_id, schedule_value)
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a cron job by ID."""
        cursor = self._conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def remove_job_by_name(self, name: str) -> int:
        """Remove cron job(s) by name. Returns number of jobs removed."""
        cursor = self._conn.execute("DELETE FROM cron_jobs WHERE name = ?", (name,))
        self._conn.commit()
        return cursor.rowcount

    def list_jobs(self) -> list[dict]:
        """List all active cron jobs."""
        rows = self._conn.execute(
            "SELECT id, name, message, schedule_type, schedule_value, enabled, last_status FROM cron_jobs"
        ).fetchall()
        return [dict(r) for r in rows]
