"""Structured JSON logging with a per-request id.

Every record becomes one JSON line: ts, level, logger, msg, request_id and any `extra=` fields.
Callers must never pass question text, chunk text or secrets as extras at INFO level.
"""
import contextvars
import json
import logging
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Route the root logger to stdout as JSON lines."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Libraries that log every HTTP call (model hub checks, provider requests) at INFO.
    for noisy in ("httpx", "httpx2", "huggingface_hub", "sentence_transformers", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
