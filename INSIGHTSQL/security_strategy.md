# INSIGHTSQL Security Strategy

> **Status:** Core local controls are implemented and tested; this document is not a security certification. Authentication, hosted secret management, and deployment hardening are not implemented.

## API key management

- Read `OPENAI_API_KEY` from the process environment. Local development loads `.env` through `python-dotenv`; keep `.env` out of version control and restrict filesystem permissions.
- Provide `.env.example` with placeholder text only. Never include a real key in source, examples, screenshots, test fixtures, prompts, error messages, or logs.
- Use a managed secret store for any hosted deployment. Rotate keys, scope access, and revoke exposed credentials promptly.
- Validate AI configuration at startup only when AI features are enabled. Database-only operations should not require an API key.

## Environment and database path protection

Use validated configuration such as `INSIGHTSQL_DB_PATH`; do not accept a filesystem path from a natural-language prompt. Resolve the configured path and verify it exists and is a file. The initial local target is `D:\SQL_APP1\DBINSIGHT\dbinsight.db`. Do not copy, migrate, recreate, seed, or write this database.

The current local implementation accepts the path only from trusted environment configuration and does not allow prompts or model output to change it. It does not enforce a fixed filesystem-root allowlist; add an explicit allowlist if the application is deployed in a shared or otherwise untrusted environment.

Use an SQLite URI created from a resolved path, for example:

```python
database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
connection = sqlite3.connect(database_uri, uri=True, timeout=5.0)
connection.execute("PRAGMA query_only = ON")
```

The path must be escaped with `Path.as_uri()` rather than interpolated as an unescaped Windows URI. Close each connection reliably.

## SQL injection prevention and validation

SQL from GPT or user input is untrusted. Do not concatenate user text into SQL. Use parameterized bindings for any values in application-authored deterministic statements. For generated SQL, where the statement itself is dynamic:

1. Parse the entire candidate with a maintained SQL parser and reject parse errors.
2. Require exactly one statement; reject trailing executable statements and statement separators that parse as additional statements.
3. Allow only an explicitly defined reporting grammar: `SELECT` and, if fully verified by the parser/policy, a read-only CTE whose terminal operation is `SELECT`.
4. Reject `INSERT`, `UPDATE`, `DELETE`, `REPLACE`, `CREATE`, `ALTER`, `DROP`, `VACUUM`, transaction control, `ATTACH`, `DETACH`, extension loading, PRAGMA, and other administrative or mutating operations.
5. Restrict referenced tables and columns to the configured allowlist. Reject unknown schemas, unsupported table-valued functions, and risky/dangerous functions.
6. Apply limits on SQL length, nesting/complexity, columns, and result size. Require deterministic limits even if GPT omits them.
7. Treat validation as an independent authorization decision; never trust the model's claim that its statement is safe.

Do not use a regex blacklist or naive first-word check as the primary validator. Keep policy tests for comments, quoted identifiers, CTEs, multi-statement input, and obfuscated or malformed syntax.

## Read-only execution and application controls

Open AI-generated reporting queries with `mode=ro`; also enable `PRAGMA query_only=ON`. Use a SQLite authorizer callback where appropriate to deny writes, schema changes, attachment, and prohibited operations as defense in depth. Execute only an approved query representation produced by the validator.

SQLite read-only mode **does not replace SQL validation and application-level controls**. It does not by itself enforce the product's table allowlist, single-statement policy, response-size limits, acceptable query complexity, or privacy rules. Both the validator and the database controls are required.

## Timeouts and result limits

- Use a short SQLite connection/busy timeout and a `set_progress_handler` callback based on a monotonic deadline to interrupt long-running virtual-machine work.
- Enforce maximum returned rows by fetching at most `max_rows + 1`; use the extra row only to indicate truncation. Bound columns, cell sizes, total serialized output, and UI rendering.
- The current provider adapter applies a request timeout and caps the response body size. A provider token budget and bounded retry policy are not implemented; add them only with explicit provider-specific limits.
- Do not retry invalid SQL, authentication failures, policy rejections, or deterministic database errors automatically.

## Minimize data sent to OpenAI

- SQL generation receives the question and necessary table/column/type/relationship metadata only. Do not send sample rows by default.
- The current application does not send query results to the provider. Any future explanation feature must require explicit opt-in and send only a bounded, privacy-reviewed subset; prefer aggregates and exclude direct identifiers and sensitive columns unless explicitly authorized.
- Avoid sending full database schemas when a smaller allowlisted schema is sufficient.
- Tell users when data will be sent to an external AI service and offer a deterministic no-AI path where feasible.
- Review retention, provider settings, and applicable organizational privacy requirements before deployment.

## Input validation and output handling

Validate request length, encoding, and supported options server-side. Treat database values and all model output as untrusted. Escape table values and render explanations as plain text; do not enable unsafe HTML or evaluate model output. Do not allow prompts or model responses to alter paths, configuration, validation policy, or tool permissions.

## Dependency and operational security

Pin and review dependencies during implementation; monitor security advisories and update through a tested change process. Limit file permissions on the database and local secrets. Keep logs free of credentials, raw prompts, SQL result contents, and personal data. For hosted use, add authentication, authorization, network controls, secret management, and rate/resource limits before exposing the service.

## Threats and safeguards summary

| Threat | Proposed safeguard |
|---|---|
| Prompt injection or malicious generated SQL | Treat output as untrusted; parse, allowlist, reject by policy; controlled repository only |
| SQL injection from user-provided values | Parameterize application-authored SQL; never interpolate question text |
| Accidental database mutation | Read-only URI, `query_only`, SQLite authorizer, strict SQL policy, temporary test databases |
| Arbitrary file/database access | Trusted path configuration, optional fixed-root allowlist for shared deployments, no prompt-controlled path |
| Excessive query or response | Deadline/progress handler, row/size limits, complexity policy |
| Secret leakage | Environment/secret store, placeholder-only example, redaction and `.env` exclusion |
| Sensitive-data disclosure to provider | Schema-only SQL-generation context; no result data is currently sent |
