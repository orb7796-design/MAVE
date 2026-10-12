"""Structured (JSON-lines) logging for the ``mave.*`` loggers, ready for centralized log collection.

Active when MAVE_LOG_FORMAT=json, which is also the default in production; development keeps plain text.
Secrets must never reach the logger: callers log route templates and status codes, not query strings or bodies.
"""
import json
import logging
import os
import sys
import time

_RESERVED = set(logging.LogRecord("x", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():  # fields passed through ``extra=``
            if k not in _RESERVED and not k.startswith("_"):
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def wants_json(env: str, fmt: str | None = None) -> bool:
    fmt = (fmt if fmt is not None else os.environ.get("MAVE_LOG_FORMAT", "")).strip().lower()
    return fmt == "json" or (fmt == "" and env == "production")


def configure(env: str) -> None:
    root = logging.getLogger("mave")
    if getattr(root, "_mave_json", False) or not wants_json(env):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    root._mave_json = True  # type: ignore[attr-defined]
