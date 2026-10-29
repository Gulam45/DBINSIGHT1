# INSIGHTSQL Testing Strategy

> **Status:** Pytest unit and temporary-SQLite integration/security tests are implemented and run locally. See the project README for the current commands and limitations.

## Test organization

Use Pytest with the current flat `tests/` layout. Shared fixtures in `tests/conftest.py` create a fresh temporary SQLite database per test or test session, populate only the minimal fixture schema/data needed, and close/remove only that temporary file during teardown. Never point fixtures at `D:\SQL_APP1\DBINSIGHT\dbinsight.db`.

## Test layers

### Unit tests

- Request validation: empty, whitespace, malformed, and over-limit questions.
- SQL parsing and policy: accepted single read-only SELECT; allowed/denied CTEs; writes, DDL, admin operations, multiple statements, unsupported functions/tables, malformed syntax, and complexity/length limits.
- Result processing: empty result, max-row truncation, oversized cell/output, NULL and supported SQLite value types.
- Service orchestration: expected call order, no execution after rejection, reviewed-example behavior, and provider-unavailable paths.
- Configuration: missing/invalid settings, path resolution, and no secret values in diagnostic output.
- Exception mapping: stable safe messages, correlation IDs, no traceback or secret leakage to the UI.
- Logging: level/event behavior and redaction of API-key-shaped values, prompts, and result contents.

### Integration tests

- Read-only connection and query execution against a temporary SQLite file.
- Schema metadata and foreign-key reporting using a small fixture schema.
- SQLite integrity and foreign-key behavior (`PRAGMA integrity_check`, `PRAGMA foreign_key_check`) on temporary fixtures.
- Query timeout/progress-handler behavior with a bounded test query.
- Row limits, empty rows, and cleanup of cursor/connection on success and failure.
- End-to-end service flow using mocked OpenAI responses and a temporary database.

## OpenAI test policy

Mock the provider adapter/client in ordinary unit and integration tests. Tests must not require a real API key, make network calls, or send test data externally. If a separate opt-in contract test is ever introduced, it must be clearly marked, disabled by default, and use a non-sensitive test project/key.

## Safety invariants to test

1. Rejected or malformed SQL never reaches the repository execution method.
2. The query repository accepts only validator-produced query objects.
3. Reporting connections use read-only mode and query-only protection.
4. Attempts at write, DDL, multi-statement, attachment, or administrative statements are rejected.
5. Result, execution, provider request timeout, and response-size limits are enforced; automatic provider retries are not implemented.
6. Secrets and sensitive content are absent from captured logs and user-facing errors.
7. No test reads, writes, migrates, recreates, or deletes the existing project database.

## Fixtures and parameterization

Use fixtures for temporary database paths, a representative schema, service dependencies, and mocked provider responses. Parameterize statement-policy tests by operation and SQL shape. Use deterministic data, explicit timeouts, and assertions on both return values and side effects (especially that a rejected query was not executed).

## Commands

From PowerShell in `D:\SQL_APP1\INSIGHTSQL` with the project environment active:

```powershell
python -m pytest
python -m pytest .\tests
python -m pytest --cov=app --cov-report=term-missing
```

The coverage command requires the optional `pytest-cov` plugin, which is not included in the current requirements. Install it only when coverage reporting is needed.

## Validation and CI expectations

Run unit tests on each change and integration tests for database/service changes. CI should not have access to production/local database files or API secrets. Set coverage expectations after baseline implementation and focus coverage on policy decisions, failure paths, and security invariants rather than a percentage alone.
