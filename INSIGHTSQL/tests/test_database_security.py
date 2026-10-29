"""Read-only SQLite and authorizer defense-in-depth tests."""

import hashlib
import sqlite3

import pytest

from insightsql.errors import DatabaseUnavailableError, QueryExecutionError, QueryTimeoutError
from insightsql.sql_validator import ApprovedQuery


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_executes_select_and_bound_parameters(read_database):
    query = ApprovedQuery("SELECT first_name FROM employees WHERE salary > :minimum_salary LIMIT 20")
    result = read_database.execute(query, {"minimum_salary": 60000})
    assert [row[0] for row in result.rows] == ["Ava", "Noah"]


def test_query_only_connection_does_not_modify_source(
    temporary_database, read_database
):
    before = digest(temporary_database)
    with pytest.raises(QueryExecutionError):
        read_database.execute(ApprovedQuery("DELETE FROM employees"))
    assert digest(temporary_database) == before


@pytest.mark.parametrize(
    "sql",
    [
        "PRAGMA foreign_keys = OFF",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT * FROM sqlite_master",
        "SELECT load_extension('extension.dll')",
        "CREATE TABLE unsafe_table (id INTEGER)",
    ],
)
def test_authorizer_denies_direct_unvalidated_sql(read_database, temporary_database, sql):
    before = digest(temporary_database)
    with pytest.raises(QueryExecutionError):
        read_database.execute(ApprovedQuery(sql))
    assert digest(temporary_database) == before


def test_source_database_is_not_created_when_missing(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    from insightsql.database_service import ReadOnlyDatabase

    database = ReadOnlyDatabase(missing, {"employees"})
    with pytest.raises(DatabaseUnavailableError):
        database.execute(ApprovedQuery("SELECT * FROM employees"))
    assert not missing.exists()


def test_query_result_limit_is_enforced(temporary_database, schema):
    from insightsql.database_service import ReadOnlyDatabase
    from insightsql.sql_validator import SqlValidator

    validator = SqlValidator(schema, max_rows=1)
    validation, approved = validator.approve("SELECT employee_id FROM employees ORDER BY employee_id")
    assert validation.valid and approved
    database = ReadOnlyDatabase(temporary_database, set(schema), max_rows=1)
    result = database.execute(approved)
    assert result.row_count == 1
    assert result.truncated


def test_query_execution_timeout_interrupts_recursion(temporary_database, schema):
    from insightsql.database_service import ReadOnlyDatabase
    from insightsql.sql_validator import SqlValidator

    validator = SqlValidator(schema, max_rows=10)
    validation, approved = validator.approve(
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
        "SELECT SUM(x) AS total FROM n"
    )
    assert validation.valid, validation.explanation
    database = ReadOnlyDatabase(temporary_database, set(schema), timeout_seconds=1, max_rows=10)
    with pytest.raises(QueryTimeoutError):
        database.execute(approved)


def test_missing_foreign_key_target_is_blocked_by_sqlite_authorizer(
    temporary_database, schema
):
    from insightsql.database_service import ReadOnlyDatabase

    database = ReadOnlyDatabase(temporary_database, set(schema))
    with pytest.raises(QueryExecutionError):
        database.execute(ApprovedQuery("SELECT * FROM sqlite_schema"))
    with sqlite3.connect(temporary_database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_empty_result_is_returned_with_columns(read_database):
    result = read_database.execute(
        ApprovedQuery(
            "SELECT employee_id, first_name FROM employees WHERE employee_id = ? LIMIT 51"
        ),
        (999,),
    )
    assert result.columns == ("employee_id", "first_name")
    assert result.rows == ()
    assert not result.truncated


def test_result_byte_limit_is_enforced(temporary_database, schema):
    from insightsql.database_service import ReadOnlyDatabase

    database = ReadOnlyDatabase(
        temporary_database,
        set(schema),
        max_rows=50,
        max_result_bytes=8,
    )
    result = database.execute(
        ApprovedQuery(
            "SELECT first_name FROM employees ORDER BY employee_id LIMIT 51"
        )
    )
    assert [row[0] for row in result.rows] == ["Ava", "Noah"]
    assert result.truncated
    assert result.truncation_reason == "byte_limit"
