from __future__ import annotations

import json
from typing import Any

from runtime import store

TERMINAL_STATUSES = {"done", "error"}


class SQLiteJobRegistry:
    """SQLite-backed registry for runtime job records and active snapshots."""

    def create_job(self, record: dict[str, Any]) -> str:
        job_id = record["id"]
        status = record.get("status") or "queued"
        created_at = record.get("created_at")
        updated_at = record.get("updated_at") or created_at
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        terminal = 1 if status in TERMINAL_STATUSES else 0
        with store.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO job_registry
                    (id, status, created_at, updated_at, record_json, snapshot_json, terminal)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (job_id, status, created_at, updated_at, payload, payload, terminal),
            )
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._fetch_row(job_id)
        if not row:
            return None
        return self._decode(row["record_json"])

    def get_active_snapshot(self, job_id: str) -> dict[str, Any] | None:
        row = self._fetch_row(job_id)
        if not row:
            return None
        snapshot = self._decode(row["snapshot_json"])
        return snapshot or self._decode(row["record_json"])

    def update_job(self, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        row = self._fetch_row(job_id)
        if not row:
            return None
        record = self._decode(row["record_json"]) or {}
        record.update(patch)
        status = record.get("status") or row["status"]
        updated_at = record.get("updated_at") or patch.get("updated_at") or row["updated_at"]
        terminal = 1 if status in TERMINAL_STATUSES else int(row["terminal"] or 0)
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with store.transaction() as conn:
            conn.execute(
                """
                UPDATE job_registry
                SET status = ?, updated_at = ?, record_json = ?, snapshot_json = ?, terminal = ?
                WHERE id = ?;
                """,
                (status, updated_at, payload, payload, terminal, job_id),
            )
        return record

    def mark_terminal(self, job_id: str) -> None:
        with store.transaction() as conn:
            conn.execute("UPDATE job_registry SET terminal = 1 WHERE id = ?;", (job_id,))

    def _fetch_row(self, job_id: str):
        with store.DB_LOCK, store.get_connection() as conn:
            return conn.execute("SELECT * FROM job_registry WHERE id = ?;", (job_id,)).fetchone()

    @staticmethod
    def _decode(value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
