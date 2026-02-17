"""
Structured JSON logging with correlation IDs.

Every log line is JSON with: timestamp, level, correlation_id, module, message, extra.
Correlation IDs are generated per-request via middleware and stored in contextvars.
"""
import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

# Context variable holding the current request's correlation ID
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context."""
    return correlation_id_ctx.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID in the current context."""
    correlation_id_ctx.set(cid)


def generate_correlation_id() -> str:
    """Generate a new correlation ID (UUID4 hex, 32 chars)."""
    return uuid.uuid4().hex


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Output format:
    {"timestamp": "...", "level": "INFO", "correlation_id": "...", "module": "...", "message": "...", ...}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "correlation_id": get_correlation_id(),
            "module": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields passed via logging calls
        for key in ("lead_id", "client_id", "phone", "source", "provider", "error_code"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


def configure_structured_logging(log_level: str = "INFO") -> None:
    """
    Replace default logging with structured JSON logging.
    Call once at application startup before any log calls.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = StructuredJsonFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicate output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add single stdout handler with JSON formatting
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
