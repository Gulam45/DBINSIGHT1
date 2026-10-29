"""Typed values passed between application layers."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    explanation: str
    sql: str | None = None


@dataclass(frozen=True)
class GeneratedQuery:
    sql: str
    explanation: str


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    elapsed_ms: float
    truncated: bool
    truncation_reason: str | None = None

    @property
    def row_count(self) -> int:
        return len(self.rows)
