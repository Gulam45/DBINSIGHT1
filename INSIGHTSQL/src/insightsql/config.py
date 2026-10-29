"""Validated environment configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from insightsql.errors import ConfigurationError


DEFAULT_DATABASE = Path(r"D:\SQL_APP1\DBINSIGHT\dbinsight.db")
DEFAULT_HISTORY = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    / "insightSQL"
    / "history.sqlite3"
)


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer.") from error
    if not 1 <= value <= maximum:
        raise ConfigurationError(f"{name} must be between 1 and {maximum}.")
    return value


@dataclass(frozen=True)
class Settings:
    database_path: Path
    history_path: Path
    api_key: str | None
    api_base_url: str
    model: str
    query_timeout_seconds: int
    max_rows: int
    max_result_bytes: int
    max_sql_length: int
    max_question_length: int
    log_level: str

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        if env_file is None:
            load_dotenv()
        else:
            load_dotenv(env_file, override=False)

        database_path = Path(
            os.getenv("INSIGHTSQL_DB_PATH", str(DEFAULT_DATABASE))
        ).expanduser()
        history_path = Path(
            os.getenv("INSIGHTSQL_HISTORY_PATH", str(DEFAULT_HISTORY))
        ).expanduser()
        base_url = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).strip().rstrip("/")
        parsed_url = urlparse(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        is_https = parsed_url.scheme == "https" and bool(parsed_url.hostname)
        is_local_http = (
            parsed_url.scheme == "http" and parsed_url.hostname in local_hosts
        )
        if (
            not (is_https or is_local_http)
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ConfigurationError("OPENAI_BASE_URL must use HTTPS (except localhost).")

        log_level = os.getenv("INSIGHTSQL_LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("INSIGHTSQL_LOG_LEVEL is not a valid logging level.")

        return cls(
            database_path=database_path.resolve(),
            history_path=history_path.resolve(),
            api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            api_base_url=base_url,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
            or "gpt-4o-mini",
            query_timeout_seconds=_positive_int("INSIGHTSQL_QUERY_TIMEOUT", 5, 120),
            max_rows=_positive_int("INSIGHTSQL_MAX_ROWS", 500, 10000),
            max_result_bytes=_positive_int(
                "INSIGHTSQL_MAX_RESULT_BYTES", 2_000_000, 50_000_000
            ),
            max_sql_length=_positive_int("INSIGHTSQL_MAX_SQL_LENGTH", 10000, 50000),
            max_question_length=_positive_int(
                "INSIGHTSQL_MAX_QUESTION_LENGTH", 2000, 10000
            ),
            log_level=log_level,
        )
