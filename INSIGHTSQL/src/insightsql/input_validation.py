"""Validation for user-submitted natural-language questions."""

from insightsql.errors import EmptyQuestionError


def validate_question(question: str, max_length: int = 2000) -> str:
    """Normalize a question and enforce its configured character limit."""
    if not isinstance(question, str):
        raise EmptyQuestionError(max_length)
    normalized = question.strip()
    if not normalized or len(normalized) > max_length:
        raise EmptyQuestionError(max_length)
    return normalized
