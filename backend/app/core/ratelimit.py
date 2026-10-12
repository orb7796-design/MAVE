"""Request rate limiting.

Two interchangeable limiters share one method, ``allow(key, limit) -> bool``:

* :class:`MemoryLimiter` – exact sliding window kept in this process. Fine for a single worker, but every worker (or
  replica) counts on its own, so the real limit becomes ``limit x workers``.
* :class:`RedisLimiter` – sliding-window *counter* in Redis, shared by all workers. It needs ``MAVE_REDIS_URL``.
  If Redis is unreachable it **fails open to the in-memory limiter** for a short while instead of failing every
  request, so a Redis outage degrades protection (per-process limits) but never takes the API down.

Redis keys hold a SHA-256 of the client key, never the raw IP address, and expire within two windows.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Any

from .redisutil import connect as redis_connect

log = logging.getLogger("mave.ratelimit")

WINDOW = 60.0


class MemoryLimiter:
    """Exact sliding window per key, in process memory."""

    blocking = False  # pure CPU, safe to call straight from the event loop
    name = "memory"

    def __init__(self, window: float = WINDOW, max_keys: int = 10_000):
        self.window, self.max_keys = window, max_keys
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if len(self._hits) > self.max_keys:  # purge idle clients so the table cannot grow forever
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                del self._hits[k]
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


class RedisLimiter:
    """Sliding-window counter shared through Redis.

    The estimate for a key is ``previous_window_count x (1 - progress_in_current_window) + current_window_count``.
    This smooths the burst a plain fixed window allows at its boundary, with one Redis round trip per request.
    Unlike :class:`MemoryLimiter`, a rejected request is still counted, so a client that keeps hammering stays blocked
    until it backs off for a window.
    """

    blocking = True  # network I/O: callers on the event loop should run ``allow`` in a thread
    name = "redis"

    def __init__(
        self,
        client: Any,
        window: float = WINDOW,
        prefix: str = "mave:rl:",
        fallback: MemoryLimiter | None = None,
        retry_after: float = 10.0,
    ):
        self.client, self.window, self.prefix = client, window, prefix
        self.fallback = fallback or MemoryLimiter(window)
        self.retry_after = retry_after
        self._down_until = 0.0

    def _key(self, key: str, bucket: int) -> str:
        return f"{self.prefix}{hashlib.sha256(key.encode('utf-8', 'replace')).hexdigest()[:32]}:{bucket}"

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if now < self._down_until:  # Redis recently failed: do not add a timeout to every request
            return self.fallback.allow(key, limit, now)
        bucket = int(now // self.window)
        progress = (now % self.window) / self.window
        cur_key, prev_key = self._key(key, bucket), self._key(key, bucket - 1)
        try:
            pipe = self.client.pipeline(transaction=True)
            pipe.incr(cur_key)
            pipe.expire(cur_key, int(self.window * 2))
            pipe.get(prev_key)
            cur, _, prev = pipe.execute()
            estimated = int(prev or 0) * (1.0 - progress) + int(cur)
            return estimated <= limit
        except Exception as exc:  # any Redis/network error -> degrade, never break the API
            if now >= self._down_until:
                log.warning("redis rate limiter unavailable (%s); using per-process limits for %ss", type(exc).__name__, int(self.retry_after))
            self._down_until = now + self.retry_after
            return self.fallback.allow(key, limit, now)


def build_limiter(redis_url: str = "") -> MemoryLimiter | RedisLimiter:
    """Redis limiter when ``redis_url`` is usable, otherwise the in-memory one. Never raises and never logs the URL."""
    client = redis_connect(redis_url, log, "rate limiting")
    return RedisLimiter(client) if client is not None else MemoryLimiter()
