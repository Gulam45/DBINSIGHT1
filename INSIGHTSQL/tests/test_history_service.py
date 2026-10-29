"""Persistent history isolation, redaction, and revalidation tests."""

import sqlite3

from insightsql.history_service import HistoryService
from insightsql.query_service import QueryService
from insightsql.sql_validator import SqlValidator


def test_history_persists_and_redacts_secrets(history, temporary_database):
    history.record(
        question=(
            "Show employees with api_key=sk-abcdefghijklmnop "
            "Authorization: Bearer abc123"
        ),
        sql="SELECT * FROM employees",
        status="success",
        result_rows=3,
        duration_ms=1.5,
    )
    record = history.list_recent()[0]
    assert "sk-abcdefghijklmnop" not in record["question"]
    assert "abc123" not in record["question"]
    assert "[REDACTED]" in record["question"]
    assert record["result_rows"] == 3
    assert history._history_path != temporary_database.resolve()


def test_history_clear_requires_service_call(history):
    history.record("question", "SELECT 1", "success")
    assert len(history.list_recent()) == 1
    history.clear()
    assert history.list_recent() == []


def test_history_database_cannot_equal_source_database(temporary_database):
    import pytest

    from insightsql.errors import HistoryError

    with pytest.raises(HistoryError):
        HistoryService(temporary_database, temporary_database)


def test_historical_sql_is_revalidated_before_rerun(
    tmp_path, history, temporary_database, schema, read_database
):
    history.record("unsafe history", "DELETE FROM employees", "failed")
    validator = SqlValidator(schema)
    service = QueryService(validator, read_database, history)
    record = history.list_recent()[0]
    validation, result = service.execute(record["question"], record["sql_text"])
    assert not validation.valid
    assert result is None
    with sqlite3.connect(temporary_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 3
