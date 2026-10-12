"""PostgreSQL access layer: connection pool, versioned migrations, full-text search schema.

Configuration: ``MAVE_DATABASE_URL`` (e.g. ``postgresql://mave:secret@localhost:5432/mave``).

Application code keeps the small, driver-neutral surface it always had: ``with db() as con:`` yields a
connection whose ``execute()`` accepts ``?`` placeholders and returns rows that can be read by column name
*or* position (``row["url"]``, ``row[0]``, ``dict(row)``). The transaction commits when the block ends
normally and rolls back when it raises.

Full-text search lives in PostgreSQL itself: ``documents.tsv`` (title weight A, body weight B, accent-stripped,
language-neutral ``simple`` configuration) with a GIN index. The spelling vocabulary is the materialized view
``docs_vocab``, rebuilt with :func:`app.search.engine.refresh_vocab` after a crawl.
"""
import re
import threading
import time
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from ..core.config import settings
from .conn import Conn, Row, _row_factory, to_pyformat  # noqa: F401  (Row, to_pyformat: re-exported)
from .migrations import MIGRATIONS

# ------------------------------------------------------------------ connection pool
_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()


def _pool(dsn: str) -> ConnectionPool:
    pool = _pools.get(dsn)
    if pool is None:
        with _pools_lock:
            pool = _pools.get(dsn)
            if pool is None:
                pool = ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=settings.db_pool_size,
                    kwargs={"row_factory": _row_factory},
                    check=ConnectionPool.check_connection,  # silently replace connections the server closed
                    timeout=30,
                    open=False,
                )
                pool.open(wait=True, timeout=30)
                _pools[dsn] = pool
    return pool


def close_pool(dsn: str) -> None:
    """Close the pool for one database (e.g. before dropping it)."""
    with _pools_lock:
        pool = _pools.pop(dsn, None)
    if pool is not None:
        pool.close()


def close_pools() -> None:
    """Close every pool (shutdown, or before dropping a database in tests)."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for p in pools:
        p.close()


@contextmanager
def db(dsn: str | None = None):
    """A pooled connection inside one transaction: commit on success, rollback on any exception."""
    with _pool(dsn or settings.database_url).connection() as raw:
        yield Conn(raw)


# ------------------------------------------------------------------ schema
SCHEMA_VERSION = max(MIGRATIONS)
_LOCK_KEY = 0x4D415645  # "MAVE": pg_advisory_xact_lock key, serialises migrations across workers


def _ensure_version_table(con: Conn) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations("
        " version INTEGER PRIMARY KEY, applied_at DOUBLE PRECISION NOT NULL)"
    )


def schema_version(con: Conn) -> int:
    """Highest applied migration (0 for a database that was never initialised)."""
    if not con.execute("SELECT to_regclass('schema_migrations') IS NOT NULL").fetchone()[0]:
        return 0
    return con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]


def migrate(con: Conn) -> int:
    """Bring the database to SCHEMA_VERSION. ``con`` must be in autocommit mode (each version is its own
    transaction). Safe to run from several workers at once. Returns the final version."""
    for version in sorted(MIGRATIONS):
        with con.transaction():
            con.execute("SELECT pg_advisory_xact_lock(?)", (_LOCK_KEY,))  # released at COMMIT/ROLLBACK
            _ensure_version_table(con)
            if con.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone():
                continue  # already applied (possibly by another worker while we waited for the lock)
            for stmt in MIGRATIONS[version]:
                con.execute(stmt)
            con.execute("INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)", (version, time.time()))
    return schema_version(con)


def init_db(dsn: str | None = None) -> None:
    with psycopg.connect(dsn or settings.database_url, autocommit=True, row_factory=_row_factory) as raw:
        migrate(Conn(raw))


_SECRET = re.compile(r"(://[^:/@]+:)[^@]*@")


def redact_dsn(dsn: str) -> str:
    """The DSN with its password hidden (safe to log)."""
    return _SECRET.sub(r"\1***@", dsn)
