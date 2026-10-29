"""Provider request behavior is tested without network access."""

import hashlib
import io
import json
import urllib.error

import pytest

from insightsql.database_service import ReadOnlyDatabase
from insightsql.errors import (
    ProviderAuthenticationError,
    DatabaseUnavailableError,
    ProviderNetworkError,
    ProviderNotConfiguredError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from insightsql.history_service import HistoryService
from insightsql.models import GeneratedQuery
from insightsql.query_service import QueryService
from insightsql.schema_service import SchemaService
from insightsql.sql_generator import SqlGenerator
from insightsql.sql_validator import SqlValidator


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        assert size == 1_000_001
        return self.content


def test_provider_sends_configured_bearer_key_and_parses_json(monkeypatch):
    api_key = "test-key-not-a-real-credential"
    response_content = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "sql": "SELECT employee_id FROM employees",
                                "explanation": "Lists employee identifiers.",
                            }
                        )
                    }
                }
            ]
        }
    ).encode("utf-8")
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data)
        return FakeResponse(response_content)

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fake_urlopen)
    generator = SqlGenerator(
        api_key=api_key,
        base_url="https://api.example.test/v1/",
        model="test-model",
        timeout_seconds=7,
    )

    generated = generator.generate(
        "Show employee identifiers",
        "employees(employee_id INTEGER)",
    )

    assert seen["authorization"] == f"Bearer {api_key}"
    assert seen["timeout"] == 7
    assert seen["body"]["model"] == "test-model"
    assert generated.sql == "SELECT employee_id FROM employees"
    assert generated.explanation == "Lists employee identifiers."


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (408, ProviderTimeoutError),
        (504, ProviderTimeoutError),
    ],
)
def test_provider_http_failures_have_safe_specific_errors(
    monkeypatch, status, error_type, caplog
):
    api_key = "private-test-key"

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            status,
            "provider failure",
            None,
            io.BytesIO(api_key.encode()),
        )

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fail)
    generator = SqlGenerator(api_key, "https://api.example.test/v1", "test-model")

    with pytest.raises(error_type) as caught:
        generator.generate("Count employees", "employees(employee_id INTEGER)")

    assert api_key not in caught.value.user_message
    assert api_key not in caplog.text


@pytest.mark.parametrize(
    "error_body",
    [
        {
            "error": {
                "message": "You exceeded your current quota.",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }
        },
        {
            "error": {
                "message": "Check your plan and billing details.",
                "type": "invalid_request_error",
                "code": None,
            }
        },
    ],
)
def test_provider_429_quota_exhaustion_is_classified_without_details(
    monkeypatch, caplog, error_body
):
    sensitive_detail = "customer-private-detail"
    payload = json.dumps(error_body).replace(
        "billing details", f"billing details {sensitive_detail}"
    ).encode()

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(payload),
        )

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fail)
    generator = SqlGenerator("private-test-key", "https://api.example.test/v1", "test-model")

    with pytest.raises(ProviderQuotaError) as caught:
        generator.generate("Count employees", "employees(employee_id INTEGER)")

    assert "billing" in caught.value.user_message.lower()
    assert "reviewed example" in caught.value.user_message.lower()
    assert sensitive_detail not in caught.value.user_message
    assert sensitive_detail not in caplog.text


def test_provider_429_rate_limit_stays_distinct_from_quota(monkeypatch):
    payload = json.dumps(
        {
            "error": {
                "message": "Rate limit reached for requests.",
                "type": "requests",
                "code": "rate_limit_exceeded",
            }
        }
    ).encode()

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(payload),
        )

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fail)
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")

    with pytest.raises(ProviderRateLimitError) as caught:
        generator.generate("Count employees", "employees(employee_id INTEGER)")

    assert "rate limit" in caught.value.user_message.lower()
    assert "billing" not in caught.value.user_message.lower()
    assert "no automatic retry" in caught.value.user_message.lower()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (TimeoutError("timeout"), ProviderTimeoutError),
        (urllib.error.URLError(TimeoutError("timeout")), ProviderTimeoutError),
        (urllib.error.URLError(OSError("offline")), ProviderNetworkError),
    ],
)
def test_provider_network_and_timeout_failures_are_classified(
    monkeypatch, failure, error_type
):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fail)
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")

    with pytest.raises(error_type):
        generator.generate("Count employees", "employees(employee_id INTEGER)")


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b'{"choices":[]}',
        b'{"choices":[{"message":{"content":"not-json"}}]}',
        b'{"choices":[{"message":{"content":"{}"}}]}',
    ],
)
def test_empty_or_malformed_provider_responses_are_rejected(monkeypatch, content):
    monkeypatch.setattr(
        "insightsql.sql_generator.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(content),
    )
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")

    with pytest.raises(ProviderResponseError):
        generator.generate("Count employees", "employees(employee_id INTEGER)")


def test_missing_api_key_explains_configuration():
    generator = SqlGenerator(None, "https://api.openai.com/v1", "test-model")

    with pytest.raises(ProviderNotConfiguredError) as caught:
        generator.generate("Count employees", "employees(employee_id INTEGER)")

    assert "OPENAI_API_KEY" in caught.value.user_message


def test_schema_retrieval_failure_is_safe(tmp_path):
    schema_service = SchemaService(tmp_path / "missing.sqlite3")

    with pytest.raises(DatabaseUnavailableError) as caught:
        schema_service.get_schema_context()

    assert "unavailable" in caught.value.user_message.lower()
    assert str(tmp_path) not in caught.value.user_message


def test_generated_sql_uses_live_schema_and_executes_only_against_temp_db(
    monkeypatch, temporary_database, schema, history
):
    request_payloads: list[dict] = []
    provider_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "sql": (
                                    "SELECT COUNT(*) AS employee_count FROM employees"
                                ),
                                "explanation": "Counts employees.",
                            }
                        )
                    }
                }
            ]
        }
    ).encode()

    def fake_urlopen(request, timeout):
        request_payloads.append(json.loads(request.data))
        return FakeResponse(provider_body)

    monkeypatch.setattr("insightsql.sql_generator.urllib.request.urlopen", fake_urlopen)
    schema_service = SchemaService(temporary_database)
    schema_context = schema_service.get_schema_context()
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")
    generated: GeneratedQuery = generator.generate(
        "Count employees", schema_context
    )
    service = QueryService(
        SqlValidator(schema_service.get_schema()),
        ReadOnlyDatabase(temporary_database, set(schema), max_rows=50),
        history,
    )

    validation, result = service.execute("Count employees", generated.sql)

    assert validation.valid
    assert result is not None
    assert result.rows == ((3,),)
    assert "employees:" in request_payloads[0]["messages"][1]["content"]
    assert "employee_id INTEGER PRIMARY KEY" in request_payloads[0]["messages"][1]["content"]
    assert "Ava" not in request_payloads[0]["messages"][1]["content"]
    assert len(request_payloads) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM employees",
        "SELECT employee_id FROM employees; DELETE FROM employees",
        "SELECT secret FROM unauthorized_table",
    ],
)
def test_generated_unsafe_sql_never_executes(
    sql, monkeypatch, temporary_database, schema, history
):
    from insightsql.database_service import ReadOnlyDatabase

    response_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"sql": sql, "explanation": ""})
                    }
                }
            ]
        }
    ).encode()
    monkeypatch.setattr(
        "insightsql.sql_generator.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(response_body),
    )
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")
    generated = generator.generate("Count employees", "employees(employee_id INTEGER)")
    service = QueryService(
        SqlValidator(schema),
        ReadOnlyDatabase(temporary_database, set(schema)),
        history,
    )
    before = hashlib.sha256(temporary_database.read_bytes()).hexdigest()

    validation, result = service.execute("Count employees", generated.sql)

    assert not validation.valid
    assert result is None
    assert hashlib.sha256(temporary_database.read_bytes()).hexdigest() == before
    assert history.list_recent()[0]["status"] == "rejected"
