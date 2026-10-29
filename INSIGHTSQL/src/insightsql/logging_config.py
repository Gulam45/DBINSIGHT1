"""Redacted application logging configuration."""

import logging
import re
import sys
import atexit


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(api[_-]?key|authorization|token)(\s*[:=]\s*)(?:Bearer\s+)?([^\s,;]+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)
_STARTUP_LOGGED = False


def _log_shutdown() -> None:
    logging.getLogger("insightsql").info("application_shutdown")


atexit.register(_log_shutdown)


class RedactionFilter(logging.Filter):
    """Mask common credential forms in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in _SECRET_PATTERNS:
            if pattern.groups:
                message = pattern.sub(r"\1\2[REDACTED]", message)
            else:
                message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure console logging once for the application."""
    global _STARTUP_LOGGED
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        root.addHandler(handler)
    for handler in root.handlers:
        if not any(isinstance(item, RedactionFilter) for item in handler.filters):
            handler.addFilter(RedactionFilter())
    if not _STARTUP_LOGGED:
        logging.getLogger("insightsql").info("application_started")
        _STARTUP_LOGGED = True
