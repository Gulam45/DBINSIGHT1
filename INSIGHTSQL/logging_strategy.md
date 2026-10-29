# INSIGHTSQL Logging Strategy

> **Status:** Console logging, startup/shutdown events, query completion/rejection/error events, and common credential redaction are implemented. Correlation IDs, complete request-stage telemetry, rotating-file logging, and hosted log management remain proposed improvements.

## Logging framework and levels

Use Python's standard `logging` module, configure handlers once during application startup, and use module-level loggers. Choose levels consistently:

| Level | Intended use |
|---|---|
| `DEBUG` | Local development diagnostics such as policy decision categories and timing breakdowns; never raw secrets or database records. |
| `INFO` | Startup/shutdown, request lifecycle transitions, successful validation, completion duration, result count, and truncation status. |
| `WARNING` | Recoverable provider degradation, bounded retry, user validation rejection, or a query rejected by policy. |
| `ERROR` | Request failure such as database, provider, or timeout error, with exception class and correlation ID. |
| `CRITICAL` | Unrecoverable startup/configuration failure or a condition requiring operator intervention. |

## Events to record

- Application startup and shutdown, environment (development/production), and non-secret configuration status.
- Request start/end, correlation ID, elapsed time, and stage outcome.
- Input validation outcome and rejection category, not the full question.
- Schema retrieval duration and success/failure, not schema values unless explicitly safe and needed.
- SQL validation outcome/reason category. Avoid logging full generated SQL by default.
- Database execution duration, bounded row count, truncation flag, and classified failure.
- OpenAI operation type, duration, retry count, and provider status/error category. Never log the API key, authorization headers, full prompt, or full completion.
- Centralized exception class and correlation ID.

## Sensitive-data rules

Never log API keys, credentials, `.env` contents, authorization headers, raw database records, or sensitive query parameters. Do not log full natural-language prompts or result sets by default; they may contain personal or confidential data. Apply a redaction filter to exception text and structured fields. Avoid user identifiers unless necessary and approved. Do not include raw SQL in user-visible errors or standard logs.

## Console and optional rotating file handlers

Console logging is the default for local Streamlit execution. A future deployment may enable a rotating file handler via validated configuration. Restrict the log directory and permissions, rotate by size or time, and retain only for an explicitly approved period. Do not commit logs or add them to support bundles without review.

## Retention and troubleshooting

Define retention by environment and data-classification policy before deployment; delete expired logs through an approved retention mechanism. Provide a correlation ID in safe error messages so an operator can find a corresponding redacted diagnostic entry. Troubleshooting should use stage names, exception types, timings, and provider status codes rather than secrets or data payloads. `DEBUG` should be temporary and access-controlled.

## Current log examples

These message shapes correspond to the current implementation:

```text
INFO insightsql application_started
INFO insightsql.database_service query_completed duration_ms=184.00 rows=20 truncated=False
WARNING insightsql.query_service query_not_executed reason=validation_rejected
ERROR insightsql.database_service query_failed error_type=OperationalError
```

Request correlation IDs and detailed validation categories are recommended additions; they are not currently emitted.
