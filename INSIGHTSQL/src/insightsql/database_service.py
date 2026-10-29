"""Controlled read-only SQLite access with engine-level restrictions."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from insightsql.errors import (
    DatabaseUnavailableError,
    QueryExecutionError,
    QueryTimeoutError,
    SqlValidationError,
)
from insightsql.models import QueryResult
from insightsql.sql_validator import ALLOWED_FUNCTIONS, ApprovedQuery

logger = logging.getLogger(__name__)

_READ_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _READ_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)


class ReadOnlyDatabase:
    """Execute validator-approved SQL against an explicitly configured database."""

    def __init__(
        self,
        database_path: Path,
        allowed_tables: set[str],
        timeout_seconds: int = 5,
        max_rows: int = 500,
        max_result_bytes: int = 2_000_000,
    ) -> None:
        self._database_path = database_path.resolve()
        self._allowed_tables = {table.lower() for table in allowed_tables}
        self._timeout_seconds = timeout_seconds
        self._max_rows = max_rows
        self._max_result_bytes = max_result_bytes

    def execute(
        self,
        query: ApprovedQuery,
        parameters: Mapping[str, Any] | tuple[Any, ...] = (),
    ) -> QueryResult:
        """Execute one approved read-only query and return at most max_rows."""
        if not isinstance(query, ApprovedQuery):
            raise SqlValidationError("Query was not approved by the SQL validator.")
        safe_parameters = self._validate_parameters(parameters)
        connection = self._connect()
        started = time.monotonic()
        deadline = started + self._timeout_seconds
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        cursor: sqlite3.Cursor | None = None
        try:
            cursor = connection.execute(query.sql, safe_parameters)
            rows: list[tuple[Any, ...]] = []
            bytes_used = 0
            truncated = False
            truncation_reason: str | None = None
            for row in cursor:
                if len(rows) >= self._max_rows:
                    truncated = True
                    truncation_reason = "row_limit"
                    break
                row_values = tuple(row)
                row_size = sum(self._value_size(value) for value in row_values)
                if bytes_used + row_size > self._max_result_bytes:
                    truncated = True
                    truncation_reason = "byte_limit"
                    break
                rows.append(row_values)
                bytes_used += row_size
            columns = tuple(column[0] for column in (cursor.description or ()))
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info(
                "query_completed duration_ms=%.2f rows=%d truncated=%s",
                elapsed_ms,
                len(rows),
                truncated,
            )
            return QueryResult(
                columns=columns,
                rows=tuple(rows),
                elapsed_ms=elapsed_ms,
                truncated=truncated,
                truncation_reason=truncation_reason,
            )
        except sqlite3.OperationalError as error:
            if time.monotonic() >= deadline or "interrupt" in str(error).lower():
                logger.warning("query_timed_out duration_limit_seconds=%d", self._timeout_seconds)
                raise QueryTimeoutError("Query execution deadline exceeded.") from error
            logger.error("query_failed error_type=%s", type(error).__name__)
            raise QueryExecutionError("SQLite could not execute the query.") from error
        except sqlite3.Error as error:
            logger.error("query_failed error_type=%s", type(error).__name__)
            raise QueryExecutionError("SQLite could not execute the query.") from error
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            finally:
                connection.set_progress_handler(None, 0)
                connection.close()

    def _connect(self) -> sqlite3.Connection:
        if not self._database_path.is_file():
            raise DatabaseUnavailableError("Configured database file does not exist.")
        connection: sqlite3.Connection | None = None
        try:
            uri = self._database_path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(
                uri, uri=True, timeout=min(2.0, float(self._timeout_seconds))
            )
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA query_only").fetchone()[0] != 1:
                connection.close()
                raise DatabaseUnavailableError("SQLite query-only mode is unavailable.")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                connection.close()
                raise DatabaseUnavailableError("SQLite foreign-key checks are unavailable.")
            if hasattr(connection, "setlimit") and hasattr(sqlite3, "SQLITE_LIMIT_LENGTH"):
                connection.setlimit(
                    sqlite3.SQLITE_LIMIT_LENGTH,
                    max(self._max_result_bytes, 1_000_000),
                )
            connection.set_authorizer(self._authorize)
            return connection
        except (sqlite3.Error, OSError, ValueError) as error:
            if connection is not None:
                connection.close()
            logger.error("database_open_failed error_type=%s", type(error).__name__)
            raise DatabaseUnavailableError("Unable to open configured database.") from error

    def _authorize(
        self,
        action: int,
        arg1: str | None,
        arg2: str | None,
        database_name: str | None,
        trigger_name: str | None,
    ) -> int:
        if action not in _READ_ACTIONS:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ:
            if (
                database_name not in {"main", None}
                or not arg1
                or arg1.lower().startswith("sqlite_")
                or arg1.lower() not in self._allowed_tables
            ):
                return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (arg2 or arg1 or "").upper()
            if function_name not in ALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    @staticmethod
    def _validate_parameters(
        parameters: Mapping[str, Any] | tuple[Any, ...],
    ) -> Mapping[str, Any] | tuple[Any, ...]:
        if not isinstance(parameters, (Mapping, tuple)):
            raise QueryExecutionError("Query parameters must be a mapping or tuple.")
        values = parameters.values() if isinstance(parameters, Mapping) else parameters
        for value in values:
            if value is not None and not isinstance(value, (str, bytes, int, float)):
                raise QueryExecutionError("Unsupported query parameter type.")
        return parameters

    @staticmethod
    def _value_size(value: Any) -> int:
        if value is None:
            return 1
        if isinstance(value, str):
            return len(value.encode("utf-8"))
        if isinstance(value, bytes):
            return len(value)
        return 16
