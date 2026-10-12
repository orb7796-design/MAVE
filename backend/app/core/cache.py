import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, ttl: float = 300, maxsize: int = 512):
        self.ttl, self.maxsize = ttl, maxsize
        self._d: OrderedDict = OrderedDict()

    def get(self, key):
        v = self._d.get(key)
        if not v:
            return None
        if v[0] < time.time():
            self._d.pop(key, None)
            return None
        self._d.move_to_end(key)
        return v[1]

    def set(self, key, value):
        self._d[key] = (time.time() + self.ttl, value)
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)


# ---------------------------------------------------------------------------------------------------------------------
# Two-level cache: this process (fast, always on) in front of an optional Redis shared by all workers.
import asyncio  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402

from .redisutil import connect as redis_connect  # noqa: E402

log = logging.getLogger("mave.cache")
MAX_VALUE_BYTES = 256 * 1024  # bigger values are only kept in-process


class SharedCache:
    """``get``/``set`` like :class:`TTLCache`, plus ``aget``/``aset`` that keep the Redis round trip off the event loop.

    * Only for data that does not depend on *who* asks (public search results, AI answers built from public sources).
    * Values must be JSON-serialisable; they are stored as JSON, never pickled, so a poisoned Redis cannot run code.
    * Keys are hashed: Redis never sees raw queries. Values are deep-copied in and out so callers cannot corrupt the cache.
    * Redis is an optimisation: any Redis error is logged once, skipped for ``retry_after`` seconds, and the
      in-process cache keeps working. A corrupt entry is treated as a miss and does not count as an outage.
    """

    def __init__(self, namespace: str, ttl: float = 300, maxsize: int = 512, client=None, retry_after: float = 10.0, clock=time.time):
        self.namespace, self.ttl, self.client = namespace, ttl, client
        self.retry_after, self._clock, self._down_until = retry_after, clock, 0.0
        self._local = TTLCache(ttl=ttl, maxsize=maxsize)

    def _key(self, key) -> str:
        raw = key if isinstance(key, str) else repr(key)
        return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:40]

    def _rkey(self, k: str) -> str:
        return f"mave:cache:{self.namespace}:{k}"

    def _usable(self) -> bool:
        return self.client is not None and self._clock() >= self._down_until

    def _failed(self, exc: Exception) -> None:
        if self._clock() >= self._down_until:
            log.warning("redis cache '%s' unavailable (%s); in-process only for %ss", self.namespace, type(exc).__name__, int(self.retry_after))
        self._down_until = self._clock() + self.retry_after

    def _redis_get(self, k: str):
        if not self._usable():
            return None
        try:
            raw = self.client.get(self._rkey(k))
        except Exception as exc:
            self._failed(exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:  # corrupt/foreign entry: a miss, not an outage
            return None

    def _redis_set(self, k: str, value) -> None:
        if not self._usable():
            return
        try:
            raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError):  # not JSON-serialisable: keep it in-process only
            return
        if len(raw) > MAX_VALUE_BYTES:
            return
        try:
            self.client.set(self._rkey(k), raw, ex=max(1, int(self.ttl)))
        except Exception as exc:
            self._failed(exc)

    # -- sync API
    def get(self, key):
        k = self._key(key)
        hit = self._local.get(k)
        if hit is None:
            hit = self._redis_get(k)
            if hit is not None:
                self._local.set(k, hit)
        return copy.deepcopy(hit) if hit is not None else None

    def set(self, key, value) -> None:
        k = self._key(key)
        self._local.set(k, copy.deepcopy(value))
        self._redis_set(k, value)

    # -- async API (use these from request handlers)
    async def aget(self, key):
        k = self._key(key)
        hit = self._local.get(k)
        if hit is None and self._usable():
            hit = await asyncio.to_thread(self._redis_get, k)
            if hit is not None:
                self._local.set(k, hit)
        return copy.deepcopy(hit) if hit is not None else None

    async def aset(self, key, value) -> None:
        k = self._key(key)
        self._local.set(k, copy.deepcopy(value))
        if self._usable():
            await asyncio.to_thread(self._redis_set, k, value)


def build_cache(namespace: str, ttl: float = 300, maxsize: int = 512) -> SharedCache:
    """A :class:`SharedCache` backed by Redis when ``MAVE_REDIS_URL`` is set, otherwise purely in-process."""
    from .config import settings  # local import: config has no dependencies, but keep this module import-light

    return SharedCache(namespace, ttl, maxsize, client=redis_connect(settings.redis_url, log, f"the '{namespace}' cache"))
