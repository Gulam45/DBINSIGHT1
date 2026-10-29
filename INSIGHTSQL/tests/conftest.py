"""Shared fixtures use temporary databases only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from insightsql.database_service import ReadOnlyDatabase
from insightsql.history_service import HistoryService
from insightsql.sql_validator import SqlValidator


@pytest.fixture
def temporary_database(tmp_path: Path) -> Path:
    import sqlite3

    database_path = tmp_path / "test_source.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE departments (
                department_id INTEGER PRIMARY KEY,
                department_name TEXT NOT NULL UNIQUE,
                annual_budget NUMERIC NOT NULL
            );
            CREATE TABLE employees (
                employee_id INTEGER PRIMARY KEY,
                department_id INTEGER NOT NULL REFERENCES departments(department_id),
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                job_title TEXT NOT NULL DEFAULT 'Staff',
                hire_date TEXT NOT NULL DEFAULT '2020-01-01',
                salary NUMERIC NOT NULL,
                employment_status TEXT NOT NULL
            );
            CREATE TABLE projects (
                project_id INTEGER PRIMARY KEY,
                project_name TEXT NOT NULL,
                project_status TEXT NOT NULL,
                start_date TEXT NOT NULL DEFAULT '2025-01-01',
                end_date TEXT,
                budget NUMERIC NOT NULL DEFAULT 0
            );
            CREATE TABLE employee_projects (
                employee_id INTEGER NOT NULL REFERENCES employees(employee_id),
                project_id INTEGER NOT NULL REFERENCES projects(project_id),
                assigned_at TEXT NOT NULL DEFAULT '2025-01-01',
                project_role TEXT NOT NULL DEFAULT 'Staff',
                hours_per_week NUMERIC NOT NULL DEFAULT 1,
                PRIMARY KEY(employee_id, project_id)
            );
            INSERT INTO departments VALUES (1, 'Engineering', 250000);
            INSERT INTO departments VALUES (2, 'Finance', 120000);
            INSERT INTO employees (
                employee_id, department_id, first_name, last_name, salary, employment_status
            ) VALUES (1, 1, 'Ava', 'Thompson', 90000, 'active');
            INSERT INTO employees (
                employee_id, department_id, first_name, last_name, salary, employment_status
            ) VALUES (2, 2, 'Noah', 'Patel', 70000, 'active');
            INSERT INTO employees (
                employee_id, department_id, first_name, last_name, salary, employment_status
            ) VALUES (3, 1, 'Mia', 'Chen', 50000, 'on_leave');
            INSERT INTO projects (project_id, project_name, project_status)
            VALUES (1, 'Data Platform', 'active');
            INSERT INTO employee_projects (employee_id, project_id) VALUES (1, 1);
            """
        )
    return database_path


@pytest.fixture
def schema() -> dict[str, dict[str, str]]:
    return {
        "departments": {
            "department_id": "INTEGER",
            "department_name": "TEXT",
            "annual_budget": "NUMERIC",
        },
        "employees": {
            "employee_id": "INTEGER",
            "department_id": "INTEGER",
            "first_name": "TEXT",
            "last_name": "TEXT",
            "job_title": "TEXT",
            "hire_date": "TEXT",
            "salary": "NUMERIC",
            "employment_status": "TEXT",
        },
        "projects": {
            "project_id": "INTEGER",
            "project_name": "TEXT",
            "project_status": "TEXT",
            "start_date": "TEXT",
            "end_date": "TEXT",
            "budget": "NUMERIC",
        },
        "employee_projects": {
            "employee_id": "INTEGER",
            "project_id": "INTEGER",
            "assigned_at": "TEXT",
            "project_role": "TEXT",
            "hours_per_week": "NUMERIC",
        },
    }


@pytest.fixture
def validator(schema: dict[str, dict[str, str]]) -> SqlValidator:
    return SqlValidator(schema, max_sql_length=10000, max_nodes=1000, max_rows=50)


@pytest.fixture
def read_database(temporary_database: Path, schema: dict[str, dict[str, str]]) -> ReadOnlyDatabase:
    return ReadOnlyDatabase(temporary_database, set(schema), timeout_seconds=5, max_rows=50)


@pytest.fixture
def history(tmp_path: Path, temporary_database: Path) -> HistoryService:
    return HistoryService(tmp_path / "history.sqlite3", temporary_database)
