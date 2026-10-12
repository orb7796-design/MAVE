"""One place that turns ``MAVE_REDIS_URL`` into a client, shared by the rate limiter and the cache.

Never raises and never logs the URL (it may contain a password). Timeouts are short on purpose: Redis is an
optimisation here, so a slow Redis must not slow every request down.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("redis", "rediss", "unix")


def connect(url: str, logger, purpose: str) -> Any | None:
    """A Redis client for ``url``, or ``None`` when Redis is not configured / not usable (the caller then keeps
    working in-process)."""
    url = (url or "").strip()
    if not url:
        return None
    if urlparse(url).scheme not in ALLOWED_SCHEMES:
        logger.warning("MAVE_REDIS_URL must start with redis://, rediss:// or unix://; %s stays in-process", purpose)
        return None
    try:
        import redis  # imported lazily: the package is only needed when Redis is configured

        return redis.Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.25, health_check_interval=30)
    except Exception as exc:
        logger.warning("cannot set up Redis for %s (%s); it stays in-process", purpose, type(exc).__name__)
        return None
