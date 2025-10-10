"""Utilities for persisting request and response logs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator

from src.config import settings


@dataclass
class LogRecord:
    """Structured representation of a triage exchange."""

    created_at: datetime
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]


def _connect() -> sqlite3.Connection:
    db_path: Path = settings.log_db_path
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL;")
    return connection


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Create the triage log table when it does not exist."""

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS triage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                request_payload TEXT NOT NULL,
                response_payload TEXT NOT NULL
            )
            """
        )
        conn.commit()


def persist_log(record: LogRecord) -> None:
    """Persist a log record to the SQLite database."""

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO triage_logs (created_at, request_payload, response_payload)
            VALUES (?, ?, ?)
            """,
            (
                record.created_at.replace(tzinfo=timezone.utc).isoformat(),
                json.dumps(record.request_payload),
                json.dumps(record.response_payload),
            ),
        )
        conn.commit()


init_db()


__all__ = ["LogRecord", "persist_log"]
