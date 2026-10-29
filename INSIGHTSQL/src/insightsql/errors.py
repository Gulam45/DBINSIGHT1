"""Application exceptions and safe user-facing error messages."""


class InsightSqlError(Exception):
    """Base class for expected application failures."""

    user_message = "The request could not be completed."


class ConfigurationError(InsightSqlError):
    """Invalid or missing application configuration."""

    user_message = "Application configuration is invalid. Check the local setup."


class DatabaseUnavailableError(InsightSqlError):
    """Configured SQLite database is missing or inaccessible."""

    user_message = "The configured database is unavailable. Check its configured path."


class SqlValidationError(InsightSqlError):
    """SQL failed parsing or policy validation."""

    user_message = "The SQL query was not permitted and was not executed."


class QueryExecutionError(InsightSqlError):
    """A read-only SQLite query failed."""

    user_message = "The database could not complete this query."


class QueryTimeoutError(QueryExecutionError):
    """A database query exceeded the configured execution deadline."""

    user_message = "The query exceeded the allowed execution time. Try a narrower query."


class EmptyQuestionError(InsightSqlError):
    """A question was empty or exceeded the configured length."""

    def __init__(self, maximum_length: int = 2000) -> None:
        self.user_message = (
            f"Enter a question of 1 to {maximum_length} characters."
        )
        super().__init__(self.user_message)


class ProviderNotConfiguredError(InsightSqlError):
    """No LLM API key was configured."""

    user_message = (
        "Natural-language SQL needs an LLM API key. Configure OPENAI_API_KEY, "
        "or choose one of the explicit example queries."
    )


class ProviderError(InsightSqlError):
    """The configured LLM provider failed or returned invalid data."""

    user_message = "The AI SQL service is unavailable. Check provider settings and try again."


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the configured credentials or account access."""

    user_message = (
        "The AI provider rejected the API key. Check that OPENAI_API_KEY is active "
        "and that the project has permission to use the selected model."
    )


class ProviderRateLimitError(ProviderError):
    """The provider request rate limit was reached."""

    user_message = (
        "The AI provider rate limit was reached. Wait briefly before submitting "
        "another request. No automatic retry was made."
    )


class ProviderQuotaError(ProviderError):
    """The provider account has insufficient quota or a billing restriction."""

    user_message = (
        "The AI provider reports that account quota or billing is exhausted. "
        "Check API usage, billing, and spending limits before trying again. "
        "Reviewed example queries remain available."
    )


class ProviderTimeoutError(ProviderError):
    """The provider request exceeded its configured timeout."""

    user_message = "The AI provider request timed out. Try again."


class ProviderNetworkError(ProviderError):
    """A network failure prevented a provider response."""

    user_message = "The AI provider could not be reached. Check the network and try again."


class ProviderResponseError(ProviderError):
    """The provider response was too large, malformed, or incomplete."""

    user_message = (
        "The AI provider returned an invalid response. Try again or check the "
        "configured model."
    )


class HistoryError(InsightSqlError):
    """Application-owned query history failed."""

    user_message = "Query history is temporarily unavailable."
