"""SQLite-aware SQL parsing and allowlist validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify

from insightsql.models import ValidationResult

logger = logging.getLogger(__name__)

ALLOWED_FUNCTIONS = frozenset(
    {
        "ABS",
        "AVG",
        "COALESCE",
        "COUNT",
        "DATE",
        "DATETIME",
        "DENSE_RANK",
        "FIRST_VALUE",
        "GROUP_CONCAT",
        "IFNULL",
        "JULIANDAY",
        "LAG",
        "LAST_VALUE",
        "LEAD",
        "LENGTH",
        "LOWER",
        "LTRIM",
        "MAX",
        "MIN",
        "NULLIF",
        "PRINTF",
        "RANK",
        "ROUND",
        "ROW_NUMBER",
        "RTRIM",
        "STRFTIME",
        "SUBSTR",
        "SUM",
        "TIME",
        "TOTAL",
        "TRIM",
        "TYPEOF",
        "UNIXEPOCH",
        "UPPER",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
    }
)
FORBIDDEN_NODE_NAMES = (
    "Alter",
    "Attach",
    "Command",
    "Create",
    "Delete",
    "Drop",
    "Insert",
    "Into",
    "LoadData",
    "Pragma",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
    "Vacuum",
)


@dataclass(frozen=True)
class ApprovedQuery:
    """SQL and bindings that passed the SQL policy boundary."""

    sql: str


class SqlValidator:
    """Validate a single read-only SELECT against live schema metadata."""

    def __init__(
        self,
        schema: Mapping[str, Mapping[str, str]],
        max_sql_length: int = 10000,
        max_nodes: int = 1000,
        max_rows: int = 500,
    ) -> None:
        self._schema = {name.lower(): columns for name, columns in schema.items()}
        self._max_sql_length = max_sql_length
        self._max_nodes = max_nodes
        self._max_rows = max_rows

    def validate(self, sql: str) -> ValidationResult:
        """Parse and validate SQL, returning a bounded approved query on success."""
        if not isinstance(sql, str) or not sql.strip():
            return ValidationResult(False, "SQL cannot be empty.")
        if len(sql) > self._max_sql_length:
            return ValidationResult(False, "SQL exceeds the configured length limit.")

        try:
            parsed = sqlglot.parse(sql, read="sqlite", error_level=ErrorLevel.RAISE)
        except (ParseError, SqlglotError) as error:
            logger.warning("sql_rejected reason=parse_error")
            return ValidationResult(False, "The SQL syntax is invalid or unsupported.")

        statements = [statement for statement in parsed if statement is not None]
        if len(statements) != 1:
            return ValidationResult(False, "Exactly one SQL statement is allowed.")

        tree = statements[0]
        if not isinstance(tree, exp.Query) or not isinstance(
            tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)
        ):
            return ValidationResult(False, "Only a read-only SELECT query is allowed.")

        for node in tree.walk():
            if any(type(node).__name__ == name for name in FORBIDDEN_NODE_NAMES):
                return ValidationResult(False, "The query contains a prohibited operation.")
            if isinstance(node, exp.Func):
                name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
                if name not in ALLOWED_FUNCTIONS:
                    return ValidationResult(
                        False, f"The SQL function {name or 'unknown'} is not approved."
                    )
            if isinstance(node, exp.Table):
                if node.db or node.catalog:
                    return ValidationResult(
                        False, "Database and schema-qualified table references are not allowed."
                    )

        node_count = sum(1 for _ in tree.walk())
        if node_count > self._max_nodes:
            return ValidationResult(False, "The query exceeds the configured complexity limit.")

        try:
            qualified = qualify(
                tree.copy(),
                dialect="sqlite",
                schema=self._schema,
                validate_qualify_columns=True,
                identify=False,
            )
        except (SqlglotError, ValueError, TypeError):
            return ValidationResult(
                False, "The query references an unknown or ambiguous table or column."
            )

        cte_names = {
            cte.alias_or_name.lower() for cte in qualified.find_all(exp.CTE)
        }
        for table in qualified.find_all(exp.Table):
            name = table.name.lower()
            if name not in self._schema and name not in cte_names:
                return ValidationResult(
                    False, f"The table {table.name!r} is not available to this application."
                )
            if name.startswith("sqlite_"):
                return ValidationResult(False, "SQLite internal tables are not accessible.")

        try:
            bounded_tree = self._bound_limit(qualified)
        except ValueError:
            return ValidationResult(
                False, "LIMIT must be a positive integer and cannot use a parameter."
            )
        approved_sql = bounded_tree.sql(dialect="sqlite", pretty=False)
        return ValidationResult(
            True,
            "SQL validated for read-only execution.",
            sql=approved_sql,
        )

    def approve(self, sql: str) -> tuple[ValidationResult, ApprovedQuery | None]:
        """Return validation result and validator-created execution token."""
        result = self.validate(sql)
        return result, ApprovedQuery(result.sql) if result.valid and result.sql else None

    def _bound_limit(self, tree: exp.Expression) -> exp.Expression:
        limit = tree.args.get("limit")
        requested = self._max_rows + 1
        if isinstance(limit, exp.Limit):
            value = limit.expression
            if isinstance(value, exp.Literal) and value.is_int:
                try:
                    requested = min(max(int(value.this), 0), self._max_rows + 1)
                except ValueError:
                    requested = self._max_rows + 1
            else:
                raise ValueError("LIMIT must be a positive integer literal.")
        tree.set(
            "limit",
            exp.Limit(expression=exp.Literal.number(requested)),
        )
        return tree
