"""Verify log redaction and safe error messages."""

import logging

from insightsql.errors import (
    DatabaseUnavailableError,
    ProviderAuthenticationError,
    ProviderError,
    QueryTimeoutError,
    SqlValidationError,
)
from insightsql.logging_config import RedactionFilter


def test_redaction_filter_masks_api_keys_and_bearer_tokens():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="api_key=sk-abcdefghijklmnop Authorization: Bearer abc123",
        args=(),
        exc_info=None,
    )
    assert RedactionFilter().filter(record)
    assert "sk-abcdefghijklmnop" not in record.getMessage()
    assert "Bearer abc123" not in record.getMessage()
    assert "abc123" not in record.getMessage()
    assert record.getMessage().count("[REDACTED]") == 2


def test_user_facing_errors_do_not_expose_internal_details():
    errors = [
        DatabaseUnavailableError(r"D:\private\database.db"),
        ProviderError("Authorization: Bearer secret"),
        QueryTimeoutError("secret query details"),
        SqlValidationError("internal parser trace"),
    ]
    for error in errors:
        assert error.user_message
        assert "secret" not in error.user_message.lower()
        assert "private" not in error.user_message.lower()
        assert "trace" not in error.user_message.lower()


def test_provider_authentication_error_explains_key_and_project_permissions():
    message = ProviderAuthenticationError().user_message.lower()
    assert "openai_api_key" in message
    assert "project" in message
    assert "permission" in message
