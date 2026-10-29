"""Streamlit workflow checks use only mocked provider responses."""

import json
import io
from pathlib import Path
import urllib.error

import pytest
from streamlit.testing.v1 import AppTest


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return self.content


def _app_test():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    return AppTest.from_file(str(app_path), default_timeout=30)


def test_arbitrary_question_generates_validates_and_runs_with_mock_provider(
    monkeypatch, temporary_database, tmp_path, caplog
):
    api_key = "private-ui-test-key"
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("INSIGHTSQL_DB_PATH", str(temporary_database))
    monkeypatch.setenv("INSIGHTSQL_HISTORY_PATH", str(tmp_path / "history.sqlite3"))
    request_payloads: list[dict] = []
    provider_body = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "sql": (
                                    "SELECT department_id, COUNT(*) AS employee_count "
                                    "FROM employees GROUP BY department_id "
                                    "ORDER BY department_id"
                                ),
                                "explanation": "Counts employees by department.",
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

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    app = _app_test().run()
    assert not app.exception

    app.text_area[0].set_value("Count employees by department").run()
    next(
        button
        for button in app.button
        if button.label == "Generate SQL and Run Query"
    ).click().run()

    assert not app.exception
    assert any(
        "Generated SQL (untrusted until validated)" in item.value
        for item in app.markdown
    )
    assert any(metric.value == "2" for metric in app.metric if metric.label == "Rows returned")
    assert len(request_payloads) == 1
    prompt = request_payloads[0]["messages"][1]["content"]
    assert "employees:" in prompt
    assert "Ava" not in prompt
    assert api_key not in prompt
    assert api_key not in caplog.text


def test_predefined_query_runs_without_provider_key_or_provider_call(
    monkeypatch, temporary_database, tmp_path
):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("INSIGHTSQL_DB_PATH", str(temporary_database))
    monkeypatch.setenv("INSIGHTSQL_HISTORY_PATH", str(tmp_path / "history.sqlite3"))
    calls = []

    def unexpected_provider_call(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Predefined query attempted to contact OpenAI")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_provider_call)
    app = _app_test().run()
    assert not app.exception
    assert any(
        "configure openai_api_key" in info.value.lower() for info in app.info
    )
    selector = next(
        item
        for item in app.selectbox
        if item.label == "Select a reviewed predefined question"
    )
    selector.select("1. Show all employees.").run()
    assert not app.exception
    assert calls == []
    next(
        button for button in app.button if button.label == "Run Predefined Query"
    ).click().run()

    assert not app.exception
    assert any(metric.value == "3" for metric in app.metric if metric.label == "Rows returned")
    assert calls == []
    assert any(
        item.value == "Ask Your Own Question (OpenAI API)"
        for item in app.subheader
    )


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (
            429,
            {
                "error": {
                    "message": "You exceeded your current quota.",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            },
        ),
        (
            429,
            {
                "error": {
                    "message": "Rate limit reached for requests.",
                    "type": "requests",
                    "code": "rate_limit_exceeded",
                }
            },
        ),
    ],
)
def test_predefined_query_remains_available_during_provider_failures(
    monkeypatch, temporary_database, tmp_path, status, body
):
    monkeypatch.setenv("OPENAI_API_KEY", "configured-mock-key")
    monkeypatch.setenv("INSIGHTSQL_DB_PATH", str(temporary_database))
    monkeypatch.setenv("INSIGHTSQL_HISTORY_PATH", str(tmp_path / "history.sqlite3"))
    calls = []

    def fail_if_called(*args, **kwargs):
        calls.append(True)
        raise urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            status,
            "Too Many Requests",
            None,
            io.BytesIO(json.dumps(body).encode()),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
    app = _app_test().run()
    assert not app.exception
    next(
        selector
        for selector in app.selectbox
        if selector.label == "Select a reviewed predefined question"
    ).select("3. Count employees in each department.").run()
    assert calls == []
    next(
        button for button in app.button if button.label == "Run Predefined Query"
    ).click().run()
    assert not app.exception
    assert calls == []
    assert any(metric.label == "Rows returned" for metric in app.metric)


def test_missing_api_key_error_is_scoped_to_ai_mode(
    monkeypatch, temporary_database, tmp_path
):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("INSIGHTSQL_DB_PATH", str(temporary_database))
    monkeypatch.setenv("INSIGHTSQL_HISTORY_PATH", str(tmp_path / "history.sqlite3"))
    calls = []
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: calls.append(True),
    )
    app = _app_test().run()
    app.text_area[0].set_value("Count employees").run()
    next(
        button
        for button in app.button
        if button.label == "Generate SQL and Run Query"
    ).click().run()

    assert not app.exception
    displayed_errors = "\n".join(error.value for error in app.error)
    assert "configure openai_api_key" in displayed_errors.lower()
    assert calls == []
    assert any(
        item.value == "Predefined Questions (Free — No API Required)"
        for item in app.subheader
    )
    assert not any(metric.label == "Rows returned" for metric in app.metric)


@pytest.mark.parametrize(
    ("error_body", "message_fragment"),
    [
        (
            {
                "error": {
                    "message": "Rate limit reached for requests.",
                    "type": "requests",
                    "code": "rate_limit_exceeded",
                }
            },
            "rate limit was reached",
        ),
        (
            {
                "error": {
                    "message": "You exceeded your current quota.",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota",
                }
            },
            "quota or billing is exhausted",
        ),
    ],
)
def test_provider_429_shows_actionable_safe_streamlit_message(
    monkeypatch, temporary_database, tmp_path, caplog, error_body, message_fragment
):
    api_key = "private-ui-test-key"
    sensitive_detail = "private-provider-response-detail"
    body = json.dumps(error_body).replace(
        "current quota", f"current quota {sensitive_detail}"
    ).encode()
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("INSIGHTSQL_DB_PATH", str(temporary_database))
    monkeypatch.setenv("INSIGHTSQL_HISTORY_PATH", str(tmp_path / "history.sqlite3"))

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://api.example.test/v1/chat/completions",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(body),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)
    app = _app_test().run()
    app.text_area[0].set_value("Count employees").run()
    assert any(
        selector.label == "Select a reviewed predefined question"
        for selector in app.selectbox
    )
    next(
        button
        for button in app.button
        if button.label == "Generate SQL and Run Query"
    ).click().run()

    displayed_errors = "\n".join(error.value for error in app.error)
    assert message_fragment in displayed_errors.lower()
    assert api_key not in displayed_errors
    assert sensitive_detail not in displayed_errors
    assert api_key not in caplog.text
    assert sensitive_detail not in caplog.text
    assert app.session_state["ai_error"] in displayed_errors
