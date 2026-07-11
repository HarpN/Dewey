from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _db_path() -> Path:
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(str(_db_path()))
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS local_backlog (
                entity_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                current_completion INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                issuer_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_table TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                result TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS replay_nonces (
                nonce TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                issuer_id TEXT NOT NULL,
                seen_at TEXT NOT NULL
            )
            """
        )
        seed_sample_row(connection)


def seed_sample_row(connection: sqlite3.Connection) -> None:
    count = connection.execute("SELECT COUNT(*) AS total FROM local_backlog").fetchone()["total"]
    if count:
        return

    connection.execute(
        """
        INSERT INTO local_backlog (entity_id, status, current_completion, notes, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("game_105", "ACTIVE", 78, "Seeded execution row.", utc_now_iso()),
    )


def nonce_exists(nonce: str) -> bool:
    with get_connection() as connection:
        row = connection.execute("SELECT nonce FROM replay_nonces WHERE nonce = ?", (nonce,)).fetchone()
        return row is not None


def register_nonce(nonce: str, correlation_id: str, issuer_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO replay_nonces (nonce, correlation_id, issuer_id, seen_at)
            VALUES (?, ?, ?, ?)
            """,
            (nonce, correlation_id, issuer_id, utc_now_iso()),
        )


def cleanup_expired_nonces(ttl_seconds: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat()
    with get_connection() as connection:
        connection.execute("DELETE FROM replay_nonces WHERE seen_at < ?", (cutoff,))


def get_entity(entity_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM local_backlog WHERE entity_id = ?", (entity_id,)).fetchone()
        return dict(row) if row else None


def update_entity(entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_entity(entity_id)
    if current is None:
        raise KeyError(f"Entity not found: {entity_id}")

    status = str(payload.get("status", current["status"]))
    completion = int(payload.get("completion", current["current_completion"]))
    if completion < 0 or completion > 100:
        raise ValueError("completion must be between 0 and 100")
    notes = str(payload.get("notes", current["notes"]))
    if len(notes) > 2000:
        raise ValueError("notes exceeds maximum length")

    with get_connection() as connection:
        # Parameterized query only, no dynamic SQL path.
        connection.execute(
            """
            UPDATE local_backlog
            SET status = ?, current_completion = ?, notes = ?, updated_at = ?
            WHERE entity_id = ?
            """,
            (status, completion, notes, utc_now_iso(), entity_id),
        )

    updated = get_entity(entity_id)
    if updated is None:
        raise RuntimeError("Entity update failed unexpectedly")
    return updated


def append_execution_log(
    *,
    correlation_id: str,
    issuer_id: str,
    nonce: str,
    action_type: str,
    target_table: str,
    entity_id: str,
    result: str,
    details: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO execution_log (
                created_at,
                correlation_id,
                issuer_id,
                nonce,
                action_type,
                target_table,
                entity_id,
                result,
                details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now_iso(),
                correlation_id,
                issuer_id,
                nonce,
                action_type,
                target_table,
                entity_id,
                result,
                details,
            ),
        )


def execution_count() -> int:
    with get_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) AS total FROM execution_log").fetchone()["total"])
