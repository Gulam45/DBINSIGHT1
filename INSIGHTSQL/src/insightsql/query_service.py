"""Orchestration that requires fresh SQL validation for every execution."""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from insightsql.errors import InsightSqlError
from insightsql.history_service import HistoryService
from insightsql.input_validation import validate_question
from insightsql.models import QueryResult, ValidationResult
from insightsql.sql_validator import SqlValidator
from insightsql.database_service import ReadOnlyDatabase

logger = logging.getLogger(__name__)
class QueryService:
    """Validate, execute, and record every query attempt."""

    def __init__(
        self,
        validator: SqlValidator,
        database: ReadOnlyDatabase,
        history: HistoryService,
    ) -> None:
        self._validator = validator
        self._database = database
        self._history = history

    def validate(self, sql: str) -> ValidationResult:
        """Validate SQL for preview without executing it."""
        return self._validator.validate(sql)

    def execute(
        self,
        question: str,
        sql: str,
        parameters: Mapping[str, Any] | tuple[Any, ...] = (),
    ) -> tuple[ValidationResult, QueryResult | None]:
        """Revalidate SQL immediately before execution and persist the outcome."""
        validation, approved = self._validator.approve(sql)
        if not validation.valid or approved is None:
            logger.warning("query_not_executed reason=validation_rejected")
            self._record_failure(
                question, sql, validation.explanation, parameters, status="rejected"
            )
            return validation, None

        logger.info("query_validation_passed")
        started = time.monotonic()
        try:
            result = self._database.execute(approved, parameters)
        except InsightSqlError as error:
            self._record_failure(
                question,
                sql,
                error.user_message,
                parameters,
                (time.monotonic() - started) * 1000,
            )
            raise
        self._history.record(
            question=question,
            sql=validation.sql or sql,
            status="success",
            result_rows=result.row_count,
            duration_ms=result.elapsed_ms,
            parameters=parameters if isinstance(parameters, Mapping) else None,
        )
        return validation, result

    def _record_failure(
        self,
        question: str,
        sql: str,
        message: str,
        parameters: Mapping[str, Any] | tuple[Any, ...],
        duration_ms: float | None = None,
        status: str = "failed",
    ) -> None:
        self._history.record(
            question=question,
            sql=sql,
            status=status,
            duration_ms=duration_ms,
            error_message=message,
            parameters=parameters if isinstance(parameters, Mapping) else None,
        )
