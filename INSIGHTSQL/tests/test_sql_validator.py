"""Allow/deny coverage for the SQLite SQL policy."""

import hashlib

import pytest

from insightsql.query_service import QueryService


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM employees",
        "SELECT COUNT(*) FROM employees",
        "SELECT first_name FROM employees WHERE salary > 60000",
        "SELECT first_name FROM employees ORDER BY last_name",
        "SELECT department_id, COUNT(*) FROM employees GROUP BY department_id",
        (
            "SELECT e.first_name, d.department_name FROM employees e "
            "JOIN departments d ON e.department_id = d.department_id"
        ),
        (
            "WITH active_staff AS (SELECT employee_id FROM employees "
            "WHERE employment_status = 'active') SELECT employee_id FROM active_staff"
        ),
        "SELECT first_name FROM employees WHERE salary > :minimum_salary",
    ],
)
def test_accepts_safe_select_queries(validator, sql):
    result = validator.validate(sql)
    assert result.valid, result.explanation
    assert result.sql
    assert "LIMIT" in result.sql.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM employees",
        "UPDATE employees SET salary = 0",
        "INSERT INTO employees VALUES (4, 1, 'A', 'B', 1, 'active')",
        "DROP TABLE employees",
        "ALTER TABLE employees ADD COLUMN test TEXT",
        "CREATE TABLE test_table (id INTEGER)",
        "REPLACE INTO employees VALUES (4, 1, 'A', 'B', 1, 'active')",
        "ATTACH DATABASE 'other.db' AS other",
        "DETACH DATABASE other",
        "PRAGMA foreign_keys = OFF",
        "VACUUM",
        "REINDEX",
        "SELECT * FROM employees; DROP TABLE employees",
        "SELECT * FROM employees; SELECT * FROM projects",
        (
            "WITH removed AS (DELETE FROM employees RETURNING employee_id) "
            "SELECT employee_id FROM removed"
        ),
        "SELECT * FROM sqlite_master",
        "SELECT * FROM main.employees",
        "SELECT * FROM missing_table",
        "SELECT missing_column FROM employees",
        "SELECT readfile('secret.txt')",
        "SELECT load_extension('extension.dll')",
        "SELECT writefile('output.txt', 'x')",
        "SELECT * FROM employees LIMIT :row_limit",
        "SELECT * FROM employees LIMIT -1",
    ],
)
def test_rejects_unsafe_or_unsupported_queries(
    validator, read_database, history, temporary_database, sql
):
    before = hashlib.sha256(temporary_database.read_bytes()).hexdigest()
    result = validator.validate(sql)
    assert not result.valid, sql
    assert result.sql is None
    service = QueryService(validator, read_database, history)
    execution_validation, query_result = service.execute("security test", sql)
    after = hashlib.sha256(temporary_database.read_bytes()).hexdigest()
    assert not execution_validation.valid
    assert query_result is None
    assert after == before


def test_rejects_overlong_sql(schema):
    from insightsql.sql_validator import SqlValidator

    validator = SqlValidator(schema, max_sql_length=30)
    result = validator.validate("SELECT first_name FROM employees " + (" " * 31))
    assert not result.valid
    assert "length" in result.explanation.lower()


def test_rejects_excessive_ast_complexity(schema):
    from insightsql.sql_validator import SqlValidator

    validator = SqlValidator(schema, max_nodes=5)
    result = validator.validate("SELECT employee_id, first_name FROM employees")
    assert not result.valid
    assert "complexity" in result.explanation.lower()


def test_validation_result_is_structured(validator):
    result = validator.validate("SELECT COUNT(*) FROM employees")
    assert result.valid is True
    assert "validated" in result.explanation.lower()
    assert result.sql
