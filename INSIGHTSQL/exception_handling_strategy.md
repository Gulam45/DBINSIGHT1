# INSIGHTSQL Exception-Handling Strategy

> **Status:** Typed application errors and safe UI messages are implemented. The table documents the intended classification; provider behavior has not been verified against a live API.

## Centralized handling

Use typed exceptions at service boundaries and map expected failures to stable UI-safe messages. The current app handles expected exceptions in the Streamlit entry point; a fully centralized mapper and request/correlation IDs are future improvements. Every failure should be explicit: never return a success-shaped empty result when the operation failed.

Internal categories:

- `InputValidationError`
- `ConfigurationError`
- `SchemaRetrievalError`
- `SqlRejectedError`
- `DatabaseAccessError`
- `QueryTimeoutError`
- `ProviderAuthenticationError`
- `ProviderRateLimitError`
- `ProviderTimeoutError`
- `ProviderNetworkError`
- `ProviderResponseError`
- `ProviderServiceError`
- `UnexpectedApplicationError`

The current implementation defines `InsightSqlError`, `ConfigurationError`, `DatabaseUnavailableError`, `SqlValidationError`, `QueryExecutionError`, `QueryTimeoutError`, `EmptyQuestionError`, `ProviderNotConfiguredError`, `ProviderError`, `ProviderAuthenticationError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderNetworkError`, `ProviderResponseError`, and `HistoryError` in `src/insightsql/errors.py`.

## Error-specific behavior

| Category | Internal response | Safe user-facing behavior |
|---|---|---|
| Input validation | Record rejection category without logging the full input | Explain which input requirement failed |
| Configuration | Fail startup or the affected feature explicitly; do not substitute a different database path | State that configuration needs attention |
| Database connection/schema | Log exception type and sanitized context; stop the request | State that the configured data source could not be read |
| Invalid/rejected SQL | Record policy rejection reason; never pass it to SQLite | State that the proposed query was not permitted and was not executed |
| SQLite query error | Classify and log without exposing records or raw provider output | Show a generic query failure |
| Query timeout | Interrupt via progress handler, close resources, and report timeout distinctly | State that the query exceeded the allowed time |
| OpenAI authentication/authorization | Do not retry; mark AI unavailable | State that credentials or account API access need attention |
| OpenAI HTTP 429 with recognized quota/billing code or message | Do not retry; do not expose raw provider response | State that account quota/billing is exhausted and direct the user to usage, billing, and spending limits |
| OpenAI HTTP 429 without a recognized quota/billing signal | Do not retry automatically in the current implementation | State that the request rate limit was reached and suggest waiting before submitting again |
| OpenAI timeout/network failure | Stop the request; do not retry automatically in the current implementation | State that the provider timed out or could not be reached |
| OpenAI malformed/oversized response | Reject the response and do not execute SQL | State that the provider returned an invalid response |
| Unexpected application error | Log diagnostic details only to protected internal logs with secrets redacted; return no raw traceback | Show a generic error |

## Safe errors and internal diagnostics

User messages must not disclose file paths, SQL text, schema values, credentials, provider headers, raw exception messages, or record data. Logs may include sanitized exception class, stage, duration, and provider status code. Redaction must apply to exception messages and structured fields as well as ordinary log strings.

Do not swallow exceptions with broad catches that return empty results. Catch expected exceptions at the narrowest boundary, translate them to typed application errors, and allow truly unexpected failures to reach the central UI boundary after recording diagnostics.

## Resource cleanup and transaction handling

Use context managers or `try/finally` to close SQLite cursors and connections on success, validation failure, database error, and timeout. Reporting connections are read-only and should not start write transactions. If future application-owned writes are added, isolate them from AI-generated reporting, use explicit transactions with rollback on error, and do not apply them to the existing Employee Management System database without a separately approved migration plan.

## Retry policy

The current provider adapter does not retry automatically. If retries are introduced later, restrict them to idempotent transient provider operations, respect the total request deadline, and cap attempts. Never retry invalid requests, rejected SQL, authentication/authorization failures, arbitrary SQLite errors, or timeouts in a way that duplicates unbounded work.
