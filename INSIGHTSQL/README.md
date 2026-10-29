# insightSQL

**Ask your database in plain English.** insightSQL is a local Streamlit application that proposes SQLite queries from natural-language questions, validates each candidate, and runs approved queries using a read-only database connection.

> **Security and implementation status:** The application is implemented as a local-use project with defense-in-depth controls and automated tests. It is not a security certification or guarantee. Review [security limitations](#security-limitations) before using it with sensitive or shared data.

## Features

- Streamlit natural-language question form for arbitrary database questions, plus reviewed examples.
- Configurable OpenAI-compatible chat-completions provider; no key is hardcoded.
- Explicit examples when no provider is configured; arbitrary natural-language generation requires an API key.
- SQLGlot SQLite parsing and policy validation before every execution, including historical reruns.
- One read-only `SELECT` query only, with table/column checks, function allowlisting, complexity/length limits, row limits, and a query deadline.
- SQLite read-only URI, `query_only`, foreign-key setting verification, and a restrictive authorizer callback.
- Result table, row count, timing, truncation status, empty-result messaging, and CSV export from the already executed result.
- Local query history stored in an application-owned SQLite database separate from the source.
- Sanitized user-facing errors, console logging, and tests using temporary databases.

## Source database

The default database is the existing file:

```text
D:\SQL_APP1\DBINSIGHT\dbinsight.db
```

The application inspects its live schema at startup. It does not copy, create, migrate, seed, or write this database. Change the source only through the trusted local `INSIGHTSQL_DB_PATH` setting.

## Architecture

```text
Streamlit UI
    -> Python query service
       -> schema service / configurable OpenAI-compatible SQL generator
       -> SQLGlot validator (required for every candidate)
       -> read-only sqlite3 execution with authorizer, timeout, and row cap
       -> pandas result display and CSV from the same result
       -> separate application-owned history database
```

Responsibilities are separated under `src/insightsql`: configuration, schema retrieval, SQL generation, validation, read-only execution, orchestration, history, errors, and logging. The previous architecture documents remain available in this folder:

- [System architecture](./architecture.md)
- [Component design](./component_diagram.md)
- [Data flow](./data_flow_diagram.md)
- [Folder structure](./folder_structure.md)
- [Security strategy](./security_strategy.md)
- [Logging strategy](./logging_strategy.md)
- [Exception handling](./exception_handling_strategy.md)
- [Testing strategy](./testing_strategy.md)
- [Mermaid diagram reference](./diagrams.md)

## Project structure

```text
insightSQL/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── src/
│   └── insightsql/
│       ├── config.py
│       ├── database_service.py
│       ├── errors.py
│       ├── history_service.py
│       ├── input_validation.py
│       ├── logging_config.py
│       ├── models.py
│       ├── query_service.py
│       ├── schema_service.py
│       ├── sql_generator.py
│       └── sql_validator.py
└── tests/
    ├── conftest.py
    ├── test_app_workflow.py
    ├── test_database_security.py
    ├── test_history_service.py
    ├── test_logging_and_errors.py
    ├── test_query_service.py
    ├── test_sql_generator.py
    └── test_sql_validator.py
```

This folder also contains the separate architecture documents. On Windows, `INSIGHTSQL` and `insightSQL` are the same folder name; the application and docs intentionally coexist here.

## Prerequisites

- Windows 10/11 and PowerShell.
- Python 3.11 or newer. Python 3.12 is recommended for the supplied setup.
- The source SQLite file at the configured path.
- An OpenAI-compatible API key only for arbitrary natural-language SQL generation. The app can run reviewed example queries without a key.
- The source database was inspected read-only and currently contains 5 departments, 20 employees, 10 projects, and 18 employee-project assignments.

## Windows and PowerShell installation

From a new PowerShell terminal:

```powershell
Set-Location 'D:\SQL_APP1\INSIGHTSQL'
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    py -3.12 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .\.env)) {
    Copy-Item .env.example .env
}
notepad .env
```

If `py -3.12` is unavailable but `python` is a Python 3.11+ interpreter, replace the venv command with:

```powershell
python -m venv .venv
```

In VS Code, choose **Python: Select Interpreter** and select `D:\SQL_APP1\INSIGHTSQL\.venv\Scripts\python.exe`.

If PowerShell blocks activation, use the venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run .\app.py
```

## Environment configuration and LLM provider

Edit the local `.env` file. The setup command creates it only when it is absent; it does not overwrite existing keys. `.env.example` contains placeholders only and `.env` is ignored by Git.

```dotenv
OPENAI_API_KEY=replace-with-your-local-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
INSIGHTSQL_DB_PATH=D:\SQL_APP1\DBINSIGHT\dbinsight.db
INSIGHTSQL_QUERY_TIMEOUT=5
INSIGHTSQL_MAX_ROWS=500
INSIGHTSQL_MAX_RESULT_BYTES=2000000
INSIGHTSQL_MAX_SQL_LENGTH=10000
INSIGHTSQL_MAX_QUESTION_LENGTH=2000
INSIGHTSQL_LOG_LEVEL=INFO
```

The existing provider adapter uses Python's standard-library HTTP client to call an OpenAI-compatible `/chat/completions` endpoint and requests JSON with separate `sql` and `explanation` fields. The official OpenAI Python SDK is not installed or required by this existing adapter, so no dependency was added. `OPENAI_BASE_URL` and `OPENAI_MODEL` can be changed for a compatible provider. Never put a real key in source, screenshots, tests, or logs. If a custom endpoint is used, verify that it supports the requested API shape and apply your organization's data-sharing policy.

Optional: set `INSIGHTSQL_HISTORY_PATH` to an application-owned local path. By default, history is placed under the current user's local application data directory. Do not set it to the source DB path.

The application does not create or replace `.env`. If the file is absent, create it locally by copying the placeholder file, then edit it without sharing its contents:

```powershell
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
notepad .\.env
```

Alternatively, enter the key securely for the current PowerShell session (Streamlit inherits the variable when started from this session):

```powershell
$secureKey = Read-Host 'OpenAI API key' -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
```

## Run the application

```powershell
Set-Location 'D:\SQL_APP1\INSIGHTSQL'
.\.venv\Scripts\Activate.ps1
streamlit run .\app.py
```

Streamlit prints a local URL, typically `http://localhost:8501`. Open it in your browser.

## Using natural-language queries

1. Enter any database-related question, for example “Which department has the highest average employee salary?”.
2. Select **Generate SQL and Run Query**. The provider receives only the question and dynamically retrieved schema metadata; it never receives table rows or query results.
3. The application treats the candidate as untrusted, displays its validation status and final bounded SQL, and executes only after parser validation succeeds. Rejected SQL is never executed.
4. Review the result table, returned-row count, duration, and truncation warning. CSV download uses only the result already fetched; it does not rerun SQL.
5. Without an API key, select and load an explicit reviewed example, inspect it, and select **Execute validated SQL**. The same validator and read-only executor are used.
6. Browse history, reuse a question, or request a historical rerun. Historical SQL always passes fresh validation.

The built-in examples cover employees, department joins and counts, active projects, a salary threshold, unassigned employees, project assignment counts, and department budgets. They remain available when the key is missing or the provider is unavailable. In no-key mode the app clearly indicates that arbitrary natural-language generation is unavailable rather than applying a rule-based fallback.

The OpenAI-compatible provider call has a bounded timeout and response size. Authentication/authorization failures, request rate limits, quota/billing exhaustion, timeouts, network errors, and malformed provider responses receive distinct safe messages. For HTTP 429 responses, the app distinguishes quota/billing exhaustion only when a recognized error code or message identifies it; otherwise it reports a rate limit. Provider response details are not shown or logged. No automatic retries or query-repair attempts are made. Provider availability has not been verified with a live API request unless a real request is separately confirmed.

## SQL security restrictions

- SQLGlot parses exactly one SQLite query; only read-only `SELECT`/read-only CTE forms are accepted.
- Writes, DDL, transaction/administrative statements, multiple statements, unauthorized schemas/tables/columns, SQLite internal tables, and unapproved functions are rejected.
- SQLite is opened with URI `mode=ro`, then `query_only` and foreign-key behavior are verified. The authorizer denies write operations, attachments, unsafe functions, and unapproved table reads.
- A progress-handler deadline and row/byte limits bound execution/output.
- SQLite read-only mode alone does not replace parsing, validation, allowlisting, parameter binding, or application-level limits.
- `.env` API credentials are not sent to SQLite or stored in history.

## Query history

History is held in an application-owned SQLite database, separate from the source database. Entries include timestamp, redacted question and SQL, execution status, row count, duration, and sanitized error. Scalar bind parameters for reviewed examples may be stored to support rerun. Common API-key/Bearer token forms are redacted; avoid entering secrets or personal data in questions because history is local but persistent. The sidebar offers question reuse, revalidated SQL rerun, and a confirmation step before clearing history.

## Troubleshooting

| Symptom | Action |
|---|---|
| Database unavailable | Check that `INSIGHTSQL_DB_PATH` points to an existing readable SQLite file; the app will not create it. |
| AI setup message | Add a valid `OPENAI_API_KEY` to local `.env` and restart Streamlit, or use a reviewed example. |
| Provider authentication or access error | Verify `OPENAI_API_KEY` and account API permissions. |
| Provider rate limit error | Wait before submitting another request; no automatic retry is made. |
| Provider quota/billing error | Check account usage, billing, and spending limits. Reviewed examples remain available without another API request. |
| Provider timeout/network error | Check network access and try again. |
| Invalid provider response | Check that the selected model and endpoint support the configured JSON chat-completions request. |
| Provider error | Verify API key, base URL, model, network access, and provider compatibility; the actual provider was not live-tested without a key. |
| SQL rejected | Inspect the validation explanation. Only one approved read-only query over the discovered schema can run. |
| Query timeout | Narrow filters or joins; increase `INSIGHTSQL_QUERY_TIMEOUT` only within the configured maximum. |
| Result truncated | Add more selective filters or grouping; `INSIGHTSQL_MAX_ROWS` has a hard configuration upper bound. |
| PowerShell activation blocked | Run `.venv\Scripts\python.exe` directly as shown above. |
| History error | Check write permissions for the local application data directory or configure `INSIGHTSQL_HISTORY_PATH` to a writable separate location. |

## Automated tests

Install dependencies as above, then:

```powershell
python -m pytest
python -m pytest .\tests\test_sql_validator.py
python -m pytest .\tests\test_database_security.py
python -m pytest .\tests\test_query_service.py
python -m pytest .\tests\test_history_service.py
python -m pytest .\tests\test_logging_and_errors.py
```

Tests create disposable databases under pytest temporary directories. Destructive SQL test cases run only against these temporary databases, never `DBINSIGHT\dbinsight.db`.

## Security limitations

This is a local single-user application, not an independently audited security product. SQLGlot parsing and SQLite's authorizer are defense-in-depth but cannot guarantee safe behavior against every parser edge case, SQLite extension/build difference, compromised dependency, malicious provider, local malware, or hostile filesystem configuration. The app does not implement user authentication, multi-tenant isolation, network deployment hardening, or centralized secret management. Review dependencies, permissions, provider data handling, and threat model before use with sensitive or shared data. Keep the application updated and do not expose its Streamlit server to untrusted networks.
