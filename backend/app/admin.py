"""Admin dashboard data layer (Master Plan v1.0, phase 9).

Everything here takes an open connection from ``app.db.db()`` and is free of FastAPI, so it is unit
tested directly. Authorization (X-Admin-Key or an admin-role user's Bearer token) lives in app/api/deps.py; every
state-changing action is written to audit_log with the actor that performed it.
"""
import time

from .core.config import settings
from .crawler import normalize_url
from .db import Conn, schema_version

MAX_SEEDS = 500
ROLES = ("user", "admin")


class AdminError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail, self.status = detail, status


# ------------------------------------------------------------------ audit log
def audit(con: Conn, action: str, detail: str = "", actor: str = "admin-key") -> None:
    con.execute(
        "INSERT INTO audit_log(ts, actor, action, detail) VALUES(?,?,?,?)",
        (time.time(), actor[:60], action[:60], detail[:500]),
    )


def list_audit(con: Conn, limit: int = 100) -> list[dict]:
    rows = con.execute(
        "SELECT ts, actor, action, detail FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ crawl seeds
def list_seeds(con: Conn) -> list[dict]:
    rows = con.execute("SELECT url, enabled, added_at FROM seeds ORDER BY added_at DESC").fetchall()
    return [{"url": r["url"], "enabled": bool(r["enabled"]), "added_at": r["added_at"]} for r in rows]


def enabled_seed_urls(con: Conn) -> list[str]:
    return [r["url"] for r in con.execute("SELECT url FROM seeds WHERE enabled=1 ORDER BY added_at")]


def add_seed(con: Conn, url: str) -> str:
    norm = normalize_url(url or "")
    if not norm:
        raise AdminError("Seed must be a valid http(s) URL")
    if con.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] >= MAX_SEEDS:
        raise AdminError(f"At most {MAX_SEEDS} seeds", 409)
    con.execute(
        "INSERT INTO seeds(url, enabled, added_at) VALUES(?,1,?) ON CONFLICT(url) DO UPDATE SET enabled=1",
        (norm, time.time()),
    )
    return norm


def set_seed_enabled(con: Conn, url: str, enabled: bool) -> None:
    cur = con.execute("UPDATE seeds SET enabled=? WHERE url=?", (1 if enabled else 0, url))
    if cur.rowcount == 0:
        raise AdminError("Seed not found", 404)


def remove_seed(con: Conn, url: str) -> None:
    if con.execute("DELETE FROM seeds WHERE url=?", (url,)).rowcount == 0:
        raise AdminError("Seed not found", 404)


# ------------------------------------------------------------------ crawler / index
def crawl_errors(con: Conn, limit: int = 100) -> list[dict]:
    rows = con.execute(
        """SELECT url, status, attempts, last_error, added_at FROM frontier
           WHERE status IN ('failed','blocked','gone') OR (status='pending' AND attempts > 0)
           ORDER BY added_at DESC LIMIT ?""",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


def top_domains(con: Conn, limit: int = 20) -> list[dict]:
    rows = con.execute(
        "SELECT domain, COUNT(*) AS documents FROM documents GROUP BY domain ORDER BY documents DESC, domain LIMIT ?",
        (max(1, min(limit, 100)),),
    ).fetchall()
    return [dict(r) for r in rows]


def language_breakdown(con: Conn) -> list[dict]:
    rows = con.execute(
        "SELECT COALESCE(lang,'unknown') AS lang, COUNT(*) AS documents FROM documents GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ search analytics
def query_analytics(con: Conn, days: int = 7, top: int = 10) -> dict:
    days = max(1, min(days, 90))
    since = time.time() - days * 86400
    per_day = con.execute(
        "SELECT to_char(to_timestamp(ts) AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day, COUNT(*) AS n"
        " FROM query_log WHERE ts >= ? GROUP BY day ORDER BY day",
        (since,),
    ).fetchall()
    top_q = con.execute(
        "SELECT query, COUNT(*) AS n FROM query_log WHERE ts >= ? GROUP BY query ORDER BY n DESC, query LIMIT ?",
        (since, max(1, min(top, 50))),
    ).fetchall()
    total = con.execute("SELECT COUNT(*) FROM query_log WHERE ts >= ?", (since,)).fetchone()[0]
    return {
        "days": days,
        "total": total,
        "per_day": [dict(r) for r in per_day],
        "top_queries": [dict(r) for r in top_q],
    }


# ------------------------------------------------------------------ users
def list_users(con: Conn, limit: int = 50, offset: int = 0, q: str = "") -> dict:
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    where, args = "", []
    q = (q or "").strip().lower()
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where, args = "WHERE lower(u.email) LIKE ? ESCAPE '\\'", [f"%{esc}%"]
    total = con.execute(f"SELECT COUNT(*) FROM users u {where}", args).fetchone()[0]
    now = time.time()
    rows = con.execute(
        f"""SELECT u.id, u.email, u.email_verified, u.created_at, u.disabled_at, u.role,
                   (SELECT COUNT(*) FROM sessions s
                     WHERE s.user_id=u.id AND s.revoked_at IS NULL AND s.expires_at > ?) AS active_sessions
            FROM users u {where} ORDER BY u.id DESC LIMIT ? OFFSET ?""",
        [now, *args, limit, offset],
    ).fetchall()
    items = [
        {
            "id": r["id"],
            "email": r["email"],
            "email_verified": bool(r["email_verified"]),
            "created_at": r["created_at"],
            "disabled": r["disabled_at"] is not None,
            "role": r["role"],
            "active_sessions": r["active_sessions"],
        }
        for r in rows
    ]
    return {"total": total, "items": items}


def revoke_user_sessions(con: Conn, user_id: int) -> int:
    if con.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
        raise AdminError("User not found", 404)
    cur = con.execute(
        "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (time.time(), user_id)
    )
    return cur.rowcount


def set_user_disabled(con: Conn, user_id: int, disabled: bool, actor_user_id: int | None = None) -> int:
    """Disable (blocks login/refresh/every API call at once, revokes all sessions) or re-enable an account.
    Returns the number of sessions revoked (0 when enabling). Data is kept either way.
    ``actor_user_id`` is the signed-in admin performing it (None for the admin key): nobody disables themselves."""
    if disabled and actor_user_id is not None and actor_user_id == user_id:
        raise AdminError("You cannot disable your own account", 400)
    now = time.time()
    cur = con.execute("UPDATE users SET disabled_at=? WHERE id=?", (now if disabled else None, user_id))
    if cur.rowcount == 0:
        raise AdminError("User not found", 404)
    if not disabled:
        return 0
    return con.execute(
        "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id)
    ).rowcount


def set_user_role(con: Conn, user_id: int, role: str, actor_user_id: int | None = None) -> str:
    """Give or take away the 'admin' role. Returns the role the account now has.
    An admin cannot change their own role (no accidental self-demotion, no self-promotion path);
    the break-glass admin key (``actor_user_id=None``) can always correct any account."""
    if role not in ROLES:
        raise AdminError("Role must be 'user' or 'admin'", 400)
    if actor_user_id is not None and actor_user_id == user_id:
        raise AdminError("You cannot change your own role", 400)
    row = con.execute("SELECT role, disabled_at FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AdminError("User not found", 404)
    if role == "admin" and row["disabled_at"] is not None:
        raise AdminError("A disabled account cannot be made an admin", 400)
    con.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    return role


# ------------------------------------------------------------------ health
def system_health(con: Conn, version: str) -> dict:
    """Operational snapshot. Booleans only: never echoes a key, secret or connection string."""
    schema = schema_version(con)
    return {
        "ok": True,
        "version": version,
        "environment": settings.env,
        "schema_version": schema,
        "database": "postgresql",
        "providers": {
            "web_search": bool(settings.searxng_url),
            "ai": settings.ai_provider,  # "xai" | "anthropic" | None
            "smtp": bool(settings.smtp_host),
        },
        "config": {
            "cors_origins": len(settings.cors_origins),
            "trust_proxy": settings.trust_proxy,
            "public_url_set": bool(settings.public_url),
        },
        "time": time.time(),
    }
