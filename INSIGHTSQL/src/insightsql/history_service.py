"""Persistent, application-owned query history storage."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from insightsql.errors import HistoryError

logger = logging.getLogger(__name__)
_SECRET_VALUE = re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+)\b")
_API_FIELD = re.compile(
    r"(?i)(api[_-]?key|authorization|access[_-]?token)(\s*[:=]\s*)"
    r"(?:Bearer\s+)?([^\s,;]+)"
)


def sanitize_text(value: str | None, limit: int = 4000) -> str:
    """Redact common credential forms and cap locally stored text."""
    text = (value or "")[:limit]
    text = _API_FIELD.sub(r"\1\2[REDACTED]", text)
    return _SECRET_VALUE.sub("[REDACTED]", text)


class HistoryService:
    """Persist history outside the source database."""

    def __init__(self, history_path: Path, source_database_path: Path) -> None:
        self._history_path = history_path.resolve()
        if self._history_path == source_database_path.resolve():
            raise HistoryError("History storage must not be the source database.")
        self._initialize()

    def _initialize(self) -> None:
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._history_path, timeout=5) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS query_history (
                        history_id INTEGER PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        question TEXT NOT NULL,
                        sql_text TEXT NOT NULL,
                        parameters_json TEXT NOT NULL DEFAULT '{}',
                        status TEXT NOT NULL,
                        result_rows INTEGER,
                        duration_ms REAL,
                        error_message TEXT
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_query_history_created "
                    "ON query_history(created_at DESC)"
                )
        except (OSError, sqlite3.Error) as error:
            logger.error("history_initialize_failed error_type=%s", type(error).__name__)
            raise HistoryError("Unable to initialize query history.") from error

    def record(
        self,
        question: str,
        sql: str,
        status: str,
        result_rows: int | None = None,
        duration_ms: float | None = None,
        error_message: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> int:
        """Store a sanitized execution record and return its ID."""
        safe_parameters = {
            key: sanitize_text(value, 500) if isinstance(value, str) else value
            for key, value in (parameters or {}).items()
            if value is None or isinstance(value, (str, int, float, bool))
        }
        try:
            with sqlite3.connect(self._history_path, timeout=5) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO query_history (
                        created_at, question, sql_text, parameters_json, status,
                        result_rows, duration_ms, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now(timezone.utc).isoformat(),
                        sanitize_text(question, 2000),
                        sanitize_text(sql, 10000),
                        json.dumps(safe_parameters, ensure_ascii=True),
                        status[:30],
                        result_rows,
                        duration_ms,
                        sanitize_text(error_message, 500) if error_message else None,
                    ),
                )
                return int(cursor.lastrowid)
        except (OSError, sqlite3.Error) as error:
            logger.error("history_record_failed error_type=%s", type(error).__name__)
            raise HistoryError("Unable to save query history.") from error

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent entries, bounded to 500 records."""
        safe_limit = max(1, min(int(limit), 500))
        try:
            with sqlite3.connect(self._history_path, timeout=5) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT history_id, created_at, question, sql_text,
                           parameters_json, status, result_rows, duration_ms,
                           error_message
                    FROM query_history
                    ORDER BY history_id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as error:
            logger.error("history_read_failed error_type=%s", type(error).__name__)
            raise HistoryError("Unable to read query history.") from error

    def clear(self) -> None:
        """Remove all application-owned query history records."""
        try:
            with sqlite3.connect(self._history_path, timeout=5) as connection:
                connection.execute("DELETE FROM query_history")
        except sqlite3.Error as error:
            logger.error("history_clear_failed error_type=%s", type(error).__name__)
            raise HistoryError("Unable to clear query history.") from error

    @staticmethod
    def parameters_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
        """Decode stored scalar parameter values for revalidation/rerun."""
        try:
            parameters = json.loads(str(record.get("parameters_json", "{}")))
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(parameters, dict):
            return {}
        return {
            str(key): value
            for key, value in parameters.items()
            if value is None or isinstance(value, (str, int, float, bool))
        }
