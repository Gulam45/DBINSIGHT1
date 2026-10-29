"""Query orchestration tests for validation, input, and provider failures."""

import pytest

from insightsql.errors import EmptyQuestionError, ProviderError, ProviderNotConfiguredError
from insightsql.input_validation import validate_question
from insightsql.query_service import QueryService
from insightsql.sql_generator import SqlGenerator
from insightsql.sql_validator import SqlValidator


def test_empty_question_is_rejected():
    with pytest.raises(EmptyQuestionError):
        validate_question("   ")
    assert validate_question("  Show all employees  ") == "Show all employees"


def test_question_maximum_is_enforced():
    with pytest.raises(EmptyQuestionError) as error:
        validate_question("x" * 11, max_length=10)
    assert "10 characters" in error.value.user_message


def test_query_service_validates_before_execution(validator, read_database, history):
    service = QueryService(validator, read_database, history)
    validation, result = service.execute("count", "SELECT COUNT(*) FROM employees")
    assert validation.valid
    assert result is not None
    assert result.rows[0][0] == 3
    assert history.list_recent()[0]["status"] == "success"


def test_query_service_does_not_execute_rejected_sql(
    validator, read_database, history, temporary_database
):
    from hashlib import sha256

    before = sha256(temporary_database.read_bytes()).hexdigest()
    service = QueryService(validator, read_database, history)
    validation, result = service.execute("bad query", "DELETE FROM employees")
    assert not validation.valid
    assert result is None
    assert history.list_recent()[0]["status"] == "rejected"
    assert sha256(temporary_database.read_bytes()).hexdigest() == before


def test_sql_generator_requires_api_key():
    generator = SqlGenerator(None, "https://api.openai.com/v1", "test-model")
    with pytest.raises(ProviderNotConfiguredError):
        generator.generate("question", "employees(employee_id INTEGER)")


def test_sql_generator_rejects_empty_question_before_provider_call():
    generator = SqlGenerator(None, "https://api.openai.com/v1", "test-model")
    with pytest.raises(EmptyQuestionError):
        generator.generate("  ", "employees(employee_id INTEGER)")


def test_sql_generator_handles_provider_failure(monkeypatch):
    import urllib.error

    def fail(*args, **kwargs):
        raise urllib.error.URLError("network unavailable")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    generator = SqlGenerator("not-a-real-key", "https://api.example.test/v1", "test-model")
    with pytest.raises(ProviderError):
        generator.generate("question", "employees(employee_id INTEGER)")


def test_all_reviewed_examples_validate_and_execute(validator, read_database):
    from insightsql.sql_generator import EXAMPLE_QUERIES

    assert len(EXAMPLE_QUERIES) == 15
    for example in EXAMPLE_QUERIES:
        validation, approved = validator.approve(example.sql)
        assert validation.valid, f"{example.label}: {validation.explanation}"
        assert approved is not None
        result = read_database.execute(approved, example.parameters)
        assert result.columns


def test_sql_generator_returns_sql_and_explanation_separately(monkeypatch):
    import io
    import json

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "sql": "SELECT COUNT(*) FROM employees",
                                        "explanation": "Counts employee records.",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    generator = SqlGenerator("test-key", "https://api.example.test/v1", "test-model")
    generated = generator.generate("count employees", "employees(employee_id INTEGER)")
    assert generated.sql == "SELECT COUNT(*) FROM employees"
    assert generated.explanation == "Counts employee records."
