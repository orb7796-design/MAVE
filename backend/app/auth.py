"""Account lifecycle: registration, login, rotating refresh-token sessions, logout, password reset,
e-mail verification, preferences and account deletion.

Every function takes an open connection (``app.db.db()``) so it can be
unit-tested without FastAPI; ``app/api/`` only translates HTTP <-> these calls.

Design
- Access token: short-lived HS256 JWT (``MAVE_ACCESS_TTL``, default 15 min) bound to a server-side session id
  (``sid``). ``session_active`` is checked on every request, so logout / password reset / account deletion take
  effect immediately instead of when the token expires.
- Refresh token: random 256-bit value, only its SHA-256 is stored. It is single-use: every refresh rotates it.
  Presenting the *previous* token of a session again means it leaked (or was replayed) -> the whole session is
  revoked. Sessions slide for ``MAVE_REFRESH_TTL`` (30 days) and never live longer than 90 days.
- Reset / verification tokens: random, stored hashed, single-use, expiring (1 h / 48 h).
- Raising AuthError makes ``db()`` roll back, so paths that must persist something first (session revocation on
  token reuse) call ``con.commit()`` before raising.
"""
import hashlib
import re
import secrets
import time

import psycopg

from .core.config import settings
from .db import Conn
from .core.security import check_password, hash_password, make_token

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
RESET_TTL = 3600
VERIFY_TTL = 48 * 3600
SESSION_MAX_AGE = 90 * 86400
RESEND_COOLDOWN = 60
LANGS = {"om", "en", "am", "ar", "sw", "fr"}
THEMES = {"system", "light", "dark"}


class AuthError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ------------------------------------------------------------------ helpers
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL.fullmatch(email):
        raise AuthError(400, "Invalid email")
    return email


def validate_password(password: str, email: str) -> None:
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        raise AuthError(400, "Password must be 8-128 characters")
    low = password.lower()
    if low == email or low == email.split("@")[0]:
        raise AuthError(400, "Password is too easy to guess")


_DUMMY: tuple[bytes, bytes] | None = None


def _dummy() -> tuple[bytes, bytes]:
    """A fixed hash used to spend the same time on unknown e-mails as on real ones (no timing oracle)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("mave-timing-equalizer")
    return _DUMMY


def _open_session(con: Conn, user_id: int, now: float) -> tuple[str, str]:
    sid, refresh = secrets.token_hex(16), _new_token()
    con.execute(
        "INSERT INTO sessions(id, user_id, refresh_hash, prev_hash, created_at, rotated_at, expires_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (sid, user_id, _hash(refresh), None, now, now, now + settings.refresh_ttl),
    )
    return sid, refresh


def _pair(user_id: int, email: str, sid: str, refresh: str, verified: bool) -> dict:
    return {
        "token": make_token(user_id, email, ttl=settings.access_ttl, sid=sid),
        "refresh_token": refresh,
        "expires_in": settings.access_ttl,
        "email": email,
        "email_verified": bool(verified),
    }


def purge_expired(con: Conn, now: float | None = None) -> None:
    now = now or time.time()
    con.execute("DELETE FROM sessions WHERE expires_at < ?", (now - 7 * 86400,))
    con.execute("DELETE FROM password_resets WHERE expires_at < ?", (now - 86400,))
    con.execute("DELETE FROM email_verifications WHERE expires_at < ?", (now - 86400,))


# ------------------------------------------------------------------ register / login
def register(con: Conn, email: str, password: str, now: float | None = None) -> tuple[dict, str]:
    """Create the account and a session. Returns (token pair, raw e-mail-verification token)."""
    now = now or time.time()
    email = normalize_email(email)
    validate_password(password, email)
    salt, pw = hash_password(password)
    try:
        with con.transaction():  # savepoint: a duplicate e-mail must not poison the surrounding transaction
            uid = con.execute(
                "INSERT INTO users(email, salt, pw_hash, created_at) VALUES(?,?,?,?) RETURNING id",
                (email, salt, pw, now),
            ).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise AuthError(409, "Email already registered")
    sid, refresh = _open_session(con, uid, now)
    verify_token = _issue_verification(con, uid, now)
    return _pair(uid, email, sid, refresh, False), verify_token


def login(con: Conn, email: str, password: str, now: float | None = None) -> dict:
    now = now or time.time()
    email = (email or "").strip().lower()
    row = con.execute(
        "SELECT id, salt, pw_hash, email_verified, disabled_at FROM users WHERE email=?", (email,)
    ).fetchone()
    if row is None:
        check_password(password, *_dummy())
        raise AuthError(401, "Wrong email or password")
    if not check_password(password, row["salt"], row["pw_hash"]):
        raise AuthError(401, "Wrong email or password")
    if row["disabled_at"] is not None:  # only revealed after the password matched: no account-enumeration oracle
        raise AuthError(403, "Account disabled")
    purge_expired(con, now)
    sid, refresh = _open_session(con, row["id"], now)
    return _pair(row["id"], email, sid, refresh, row["email_verified"])


# ------------------------------------------------------------------ sessions
def refresh(con: Conn, refresh_token: str, now: float | None = None) -> dict:
    now = now or time.time()
    h = _hash(refresh_token or "")
    row = con.execute(
        "SELECT s.id, s.user_id, s.created_at, s.expires_at, s.revoked_at, u.email, u.email_verified, u.disabled_at"
        " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.refresh_hash=?",
        (h,),
    ).fetchone()
    if row is None:
        reused = con.execute("SELECT id FROM sessions WHERE prev_hash=? AND revoked_at IS NULL", (h,)).fetchone()
        if reused:  # an already-rotated token came back: assume theft, kill the session (and persist that)
            con.execute("UPDATE sessions SET revoked_at=? WHERE id=?", (now, reused["id"]))
            con.commit()
            raise AuthError(401, "Session revoked")
        raise AuthError(401, "Invalid refresh token")
    if row["revoked_at"] is not None or row["disabled_at"] is not None:
        raise AuthError(401, "Session revoked")
    if row["expires_at"] < now or now - row["created_at"] > SESSION_MAX_AGE:
        raise AuthError(401, "Session expired")
    new = _new_token()
    new_expiry = min(now + settings.refresh_ttl, row["created_at"] + SESSION_MAX_AGE)
    cur = con.execute(  # conditional update: of two concurrent refreshes with one token only one can win
        "UPDATE sessions SET refresh_hash=?, prev_hash=?, rotated_at=?, expires_at=?"
        " WHERE id=? AND refresh_hash=? AND revoked_at IS NULL",
        (_hash(new), h, now, new_expiry, row["id"], h),
    )
    if cur.rowcount != 1:
        raise AuthError(401, "Invalid refresh token")
    return _pair(row["user_id"], row["email"], row["id"], new, row["email_verified"])


def session_active(con: Conn, sid: str, user_id: int, now: float | None = None) -> bool:
    now = now or time.time()
    row = con.execute(
        "SELECT 1 FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.id=? AND s.user_id=? AND s.revoked_at IS NULL AND s.expires_at >= ? AND u.disabled_at IS NULL",
        (sid, user_id, now),
    ).fetchone()
    return row is not None


def logout(
    con: Conn,
    *,
    sid: str | None = None,
    refresh_token: str | None = None,
    user_id: int | None = None,
    everywhere: bool = False,
    now: float | None = None,
) -> None:
    """Idempotent: unknown / already-revoked sessions are not an error."""
    now = now or time.time()
    if everywhere:
        if user_id is None:
            raise AuthError(401, "Missing token")
        con.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id))
    elif sid:
        con.execute("UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, sid))
    elif refresh_token:
        h = _hash(refresh_token)
        con.execute(
            "UPDATE sessions SET revoked_at=? WHERE (refresh_hash=? OR prev_hash=?) AND revoked_at IS NULL",
            (now, h, h),
        )


# ------------------------------------------------------------------ password reset
def request_password_reset(con: Conn, email: str, now: float | None = None) -> tuple[str, str] | None:
    """Returns (email, raw token) to be mailed, or None. The HTTP layer answers identically either way."""
    now = now or time.time()
    email = (email or "").strip().lower()
    row = con.execute("SELECT id, email FROM users WHERE email=?", (email,)).fetchone()
    if row is None:
        return None
    last = con.execute("SELECT MAX(created_at) FROM password_resets WHERE user_id=?", (row["id"],)).fetchone()[0]
    if last is not None and now - last < RESEND_COOLDOWN:  # stops mail-bombing a victim
        return None
    con.execute("DELETE FROM password_resets WHERE user_id=?", (row["id"],))
    raw = _new_token()
    con.execute(
        "INSERT INTO password_resets(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
        (_hash(raw), row["id"], now, now + RESET_TTL),
    )
    return row["email"], raw


def reset_password(con: Conn, token: str, new_password: str, now: float | None = None) -> None:
    now = now or time.time()
    h = _hash(token or "")
    row = con.execute(
        "SELECT r.user_id, r.expires_at, r.used_at, u.email FROM password_resets r"
        " JOIN users u ON u.id = r.user_id WHERE r.token_hash=?",
        (h,),
    ).fetchone()
    if row is None or row["used_at"] is not None or row["expires_at"] < now:
        raise AuthError(400, "Invalid or expired reset token")
    validate_password(new_password, row["email"])  # before consuming the token: a weak password must not burn it
    cur = con.execute("UPDATE password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL", (now, h))
    if cur.rowcount != 1:
        raise AuthError(400, "Invalid or expired reset token")
    salt, pw = hash_password(new_password)
    # Receiving the mail proves control of the inbox, so the address counts as verified too.
    con.execute("UPDATE users SET salt=?, pw_hash=?, email_verified=1 WHERE id=?", (salt, pw, row["user_id"]))
    con.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, row["user_id"]))


# ------------------------------------------------------------------ e-mail verification
def _issue_verification(con: Conn, user_id: int, now: float) -> str:
    con.execute("DELETE FROM email_verifications WHERE user_id=?", (user_id,))
    raw = _new_token()
    con.execute(
        "INSERT INTO email_verifications(token_hash, user_id, created_at, expires_at) VALUES(?,?,?,?)",
        (_hash(raw), user_id, now, now + VERIFY_TTL),
    )
    return raw


def request_verification(con: Conn, user_id: int, now: float | None = None) -> tuple[str, str] | None:
    now = now or time.time()
    row = con.execute("SELECT email, email_verified FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None or row["email_verified"]:
        return None
    last = con.execute("SELECT MAX(created_at) FROM email_verifications WHERE user_id=?", (user_id,)).fetchone()[0]
    if last is not None and now - last < RESEND_COOLDOWN:
        return None
    return row["email"], _issue_verification(con, user_id, now)


def verify_email(con: Conn, token: str, now: float | None = None) -> str:
    now = now or time.time()
    h = _hash(token or "")
    row = con.execute(
        "SELECT v.user_id, v.expires_at, v.used_at, u.email FROM email_verifications v"
        " JOIN users u ON u.id = v.user_id WHERE v.token_hash=?",
        (h,),
    ).fetchone()
    if row is None or row["used_at"] is not None or row["expires_at"] < now:
        raise AuthError(400, "Invalid or expired verification token")
    cur = con.execute("UPDATE email_verifications SET used_at=? WHERE token_hash=? AND used_at IS NULL", (now, h))
    if cur.rowcount != 1:
        raise AuthError(400, "Invalid or expired verification token")
    con.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
    return row["email"]


# ------------------------------------------------------------------ profile / preferences / deletion
def get_profile(con: Conn, user_id: int) -> dict:
    row = con.execute("SELECT id, email, created_at, email_verified FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AuthError(401, "Account no longer exists")
    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
        "email_verified": bool(row["email_verified"]),
        "preferences": get_preferences(con, user_id),
    }


def get_preferences(con: Conn, user_id: int) -> dict:
    row = con.execute("SELECT lang, theme FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
    return {"lang": row["lang"], "theme": row["theme"]} if row else {"lang": None, "theme": None}


def set_preferences(con: Conn, user_id: int, lang: str | None = None, theme: str | None = None) -> dict:
    if lang is not None and lang not in LANGS:
        raise AuthError(400, "Unsupported language")
    if theme is not None and theme not in THEMES:
        raise AuthError(400, "Unsupported theme")
    cur = get_preferences(con, user_id)
    lang = cur["lang"] if lang is None else lang
    theme = cur["theme"] if theme is None else theme
    con.execute(
        "INSERT INTO user_preferences(user_id, lang, theme) VALUES(?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang, theme=excluded.theme",
        (user_id, lang, theme),
    )
    return {"lang": lang, "theme": theme}


def delete_account(con: Conn, user_id: int, password: str) -> None:
    """Permanently remove the user and everything tied to them (password re-check required)."""
    row = con.execute("SELECT salt, pw_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AuthError(401, "Account no longer exists")
    if not check_password(password, row["salt"], row["pw_hash"]):
        raise AuthError(401, "Wrong password")
    for table in ("sessions", "password_resets", "email_verifications", "history", "saved", "user_preferences"):
        con.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))  # explicit even though FKs cascade
    con.execute("DELETE FROM users WHERE id=?", (user_id,))
