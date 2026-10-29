"""Read-only retrieval of approved SQLite schema metadata."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from insightsql.errors import DatabaseUnavailableError, QueryExecutionError

logger = logging.getLogger(__name__)


class SchemaService:
    """Provide table, column, and foreign-key metadata without row data."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_schema(self) -> dict[str, dict[str, str]]:
        """Return table-to-column/type mappings from the configured database."""
        connection = self._connect_metadata()
        try:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            schema: dict[str, dict[str, str]] = {}
            for (table_name,) in rows:
                columns = connection.execute(
                    f"PRAGMA table_info({self._quote_identifier(table_name)})"
                ).fetchall()
                schema[table_name] = {
                    row[1]: row[2] or "ANY" for row in columns
                }
            if not schema:
                raise QueryExecutionError("The configured database has no user tables.")
            logger.info("schema_retrieved table_count=%d", len(schema))
            return schema
        except sqlite3.Error as error:
            logger.error("schema_read_failed error_type=%s", type(error).__name__)
            raise QueryExecutionError("Unable to read database schema.") from error
        finally:
            connection.close()

    def get_schema_context(self) -> str:
        """Return concise schema and foreign-key context without database values."""
        connection = self._connect_metadata()
        try:
            lines: list[str] = []
            tables = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
            for (table_name,) in tables:
                columns = connection.execute(
                    f"PRAGMA table_info({self._quote_identifier(table_name)})"
                ).fetchall()
                column_descriptions = [
                    f"{row[1]} {row[2] or 'ANY'}"
                    + (" PRIMARY KEY" if row[5] else "")
                    for row in columns
                ]
                lines.append(f"{table_name}: " + ", ".join(column_descriptions))
                foreign_keys = connection.execute(
                    f"PRAGMA foreign_key_list({self._quote_identifier(table_name)})"
                ).fetchall()
                for key in foreign_keys:
                    lines.append(
                        f"  FK {table_name}.{key[3]} -> {key[2]}.{key[4]}"
                    )
            if not lines:
                raise QueryExecutionError("The configured database has no user tables.")
            logger.info("schema_context_retrieved table_count=%d", len(tables))
            return "\n".join(lines)
        except sqlite3.Error as error:
            logger.error("schema_context_failed error_type=%s", type(error).__name__)
            raise QueryExecutionError("Unable to read database schema.") from error
        finally:
            connection.close()

    def _connect_metadata(self) -> sqlite3.Connection:
        if not self._database_path.is_file():
            raise DatabaseUnavailableError("Configured database file does not exist.")
        connection: sqlite3.Connection | None = None
        try:
            uri = self._database_path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=5.0)
            connection.execute("PRAGMA query_only = ON")
            return connection
        except (sqlite3.Error, OSError, ValueError) as error:
            if connection is not None:
                connection.close()
            logger.error("database_open_failed error_type=%s", type(error).__name__)
            raise DatabaseUnavailableError("Unable to open configured database.") from error

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
