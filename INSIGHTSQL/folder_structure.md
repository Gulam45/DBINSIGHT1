# insightSQL Folder Structure

> The application and architecture documents share `D:\SQL_APP1\INSIGHTSQL` (Windows treats `INSIGHTSQL` and `insightSQL` as the same folder). The existing `D:\SQL_APP1\DBINSIGHT` project remains independent and is used only as a read-only source.

## Current application tree

```text
D:\SQL_APP1\INSIGHTSQL\
├── app.py                              # Streamlit entry point
├── requirements.txt                   # Constrained runtime and test dependencies
├── .env.example                       # Placeholder configuration only
├── .gitignore                         # Local secrets, venvs, caches, histories, exports
├── README.md                          # Application installation and usage
├── architecture.md                    # Layered architecture and design
├── component_diagram.md
├── data_flow_diagram.md
├── folder_structure.md
├── security_strategy.md
├── logging_strategy.md
├── exception_handling_strategy.md
├── testing_strategy.md
├── diagrams.md
├── src\
│   └── insightsql\
│       ├── __init__.py
│       ├── config.py                   # Environment loading and validated settings
│       ├── database_service.py         # Read-only sqlite3 execution and authorizer
│       ├── errors.py                   # Typed exceptions and safe messages
│       ├── history_service.py          # Separate, sanitized history database
│       ├── input_validation.py         # Natural-language request limits
│       ├── logging_config.py           # Console logging and credential redaction
│       ├── models.py                   # Typed result/query values
│       ├── query_service.py            # Revalidation, execution, and recording
│       ├── schema_service.py           # Read-only schema/context retrieval
│       ├── sql_generator.py            # OpenAI-compatible provider and reviewed examples
│       └── sql_validator.py            # SQLGlot parsing and policy boundary
├── tests\
│   ├── conftest.py                     # Temporary SQLite fixtures
│   ├── test_app_workflow.py             # Streamlit/provider/no-key workflow tests
│   ├── test_database_security.py
│   ├── test_history_service.py
│   ├── test_logging_and_errors.py
│   ├── test_query_service.py
│   ├── test_sql_generator.py            # Mock provider, error, and SQL execution tests
│   └── test_sql_validator.py
└── .venv\                              # Local only; excluded from Git
```

The existing source project remains outside this tree:

```text
D:\SQL_APP1\DBINSIGHT\
├── dbinsight.db                        # Existing source file; reporting access is read-only
├── create_tables.sql                   # Existing file; not an insightSQL migration
├── insert_data.sql                     # Existing file; not an insightSQL seed step
└── ...                                 # Other existing project files unchanged
```

## Responsibility boundaries

| Path | Responsibility |
|---|---|
| `app.py` | Streamlit UI only: inputs, SQL review, validation state, results, exports, and history controls. |
| `src/insightsql/config.py` | Loads and validates paths, timeouts, row/byte limits, provider settings, and log level. |
| `src/insightsql/input_validation.py` | Normalizes and bounds question text before generation. |
| `src/insightsql/schema_service.py` | Opens the configured source read-only and returns schema metadata without sample rows. |
| `src/insightsql/sql_generator.py` | Provider adapter plus explicitly authored, parameterized examples; does not execute SQL. |
| `src/insightsql/sql_validator.py` | Parses one SQLite statement, checks policy/schema, and creates the approved-query value. |
| `src/insightsql/database_service.py` | Controlled read-only `sqlite3` execution, authorizer, deadline, and result bounds. |
| `src/insightsql/query_service.py` | Revalidates before execution and persists outcomes through the history service. |
| `src/insightsql/history_service.py` | Owns a distinct local history database and redacts common secret forms. |
| `src/insightsql/errors.py`, `logging_config.py` | Safe error types/messages and redacted console diagnostics. |
| `tests/` | Unit and integration/security checks using temporary databases and provider mocks. |
| `.venv/`, `.env`, history database | Local runtime state; excluded from version control and separate from the source database. |

## Windows setup and run commands

From PowerShell:

```powershell
Set-Location 'D:\SQL_APP1\INSIGHTSQL'
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the source database path in `.env`, configure a provider key only if AI generation is needed, and start the application:

```powershell
streamlit run .\app.py
```

Run the automated tests against disposable temporary databases:

```powershell
python -m pytest
```

The local history file defaults to the current user's local application data directory. It must not be pointed at `DBINSIGHT\dbinsight.db`.
