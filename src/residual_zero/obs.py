"""Production logging. Enough to diagnose a failure; never enough to leak a credential.

Two rules make this safe to turn on in a public deployment:

1. **Redaction is applied on the way out, not asked for at the call site.** Every value
   passes :func:`scrub`, which removes anything shaped like a bearer token, an API key, a
   password field or a connection-string password. A caller that logs a whole request
   context by accident still cannot print a secret.
2. **Financial values are not routine log content.** Amounts, narrations and counterparty
   strings stay out; a credit *id* is logged because diagnosing "why did this credit fail"
   needs one, and the id alone is not the money.

The output is one JSON object per line, which a hosting platform can parse without a
sidecar.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any, Iterator
from contextlib import contextmanager

LOGGER_NAME = "residual_zero"

# Patterns whose *value* must never appear. Keys are matched case-insensitively so
# `Authorization`, `authorization` and `AUTH_TOKEN` are all caught.
_SECRET_KEY = re.compile(
    r"(?i)(secret|password|passwd|token|api[_-]?key|authorization|bearer|cookie|session|"
    r"nvidia_api_key|ai_api_key|key_secret|dsn|database_url)"
)
# Values that look like a credential even under an innocent key.
_SECRET_VALUE = re.compile(
    r"(?i)(nvapi-[A-Za-z0-9_\-]{6,}|gsk_[A-Za-z0-9]{6,}|sk-[A-Za-z0-9]{12,}|"
    r"rzp_(?:live|test)_[A-Za-z0-9]{6,}|rz_pat_[A-Za-z0-9_\-]{6,}|"
    r"npg_[A-Za-z0-9]{6,}|Bearer\s+[A-Za-z0-9._\-]{8,})"
)
# postgres://user:password@host -> the password only.
_DSN_PASSWORD = re.compile(r"(?i)(?<=://)([^:/@\s]+):([^@/\s]+)(?=@)")

REDACTED = "***"


def scrub(value: Any, _key: str = "") -> Any:
    """Return ``value`` with anything credential-shaped replaced by ``***``."""
    if isinstance(value, dict):
        return {k: (REDACTED if _SECRET_KEY.search(str(k)) else scrub(v, str(k)))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v, _key) for v in value]
    if isinstance(value, str):
        if _SECRET_KEY.search(_key):
            return REDACTED
        text = _DSN_PASSWORD.sub(r"\1:" + REDACTED, value)
        return _SECRET_VALUE.sub(REDACTED, text)
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with every field scrubbed."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(scrub(extra))
        if record.exc_info:
            # The exception TYPE and message, not the frames. A stack trace belongs in the
            # server log, and this formatter is what writes it — but it is never the body
            # of an HTTP response (see console.security.install_error_handlers).
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else ""
            payload["error"] = scrub(str(record.exc_info[1] or ""))
        return json.dumps(scrub(payload), default=str, separators=(",", ":"))


def logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure_logging(level: str | None = None) -> logging.Logger:
    """Attach the JSON handler once. Idempotent, so import order does not matter."""
    log = logging.getLogger(LOGGER_NAME)
    wanted = (level or os.environ.get("RZ_LOG_LEVEL") or "INFO").strip().upper()
    log.setLevel(getattr(logging, wanted, logging.INFO))
    if not any(getattr(h, "_rz_json", False) for h in log.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        handler._rz_json = True  # type: ignore[attr-defined]
        log.addHandler(handler)
    log.propagate = False
    return log


def event(name: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log one structured event. Field values are scrubbed by the formatter."""
    logger().log(level, name, extra={"fields": fields})


def warn(name: str, **fields: Any) -> None:
    event(name, logging.WARNING, **fields)


def error(name: str, exc: BaseException | None = None, **fields: Any) -> None:
    """Log a failure with the exception type and message, never a response body."""
    logger().error(name, extra={"fields": fields}, exc_info=exc if exc else None)


@contextmanager
def timed(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Log ``name`` with a duration, and log a failure with the same fields if it raises."""
    started = time.monotonic_ns()
    carry: dict[str, Any] = {}
    try:
        yield carry
    except BaseException as exc:
        error(name + ".failed", exc, duration_ms=(time.monotonic_ns() - started) // 1_000_000,
              **fields, **carry)
        raise
    event(name, duration_ms=(time.monotonic_ns() - started) // 1_000_000, **fields, **carry)
