import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import settings


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def check_password(password: str, salt: bytes, expected: bytes) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[1], expected)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest())


def make_token(
    user_id: int, email: str, ttl: int = 30 * 86400, secret: str | None = None, sid: str | None = None
) -> str:
    """HS256 access token. ``sid`` binds it to a server-side session so logout revokes it immediately."""
    secret = secret or settings.jwt_secret
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {"sub": user_id, "email": email, "exp": int(time.time()) + ttl, "typ": "access"}
    if sid:
        claims["sid"] = sid
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    return f"{header}.{payload}.{_sign(header + '.' + payload, secret)}"


def verify_token(token: str, secret: str | None = None) -> dict | None:
    secret = secret or settings.jwt_secret
    try:
        header, payload, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(header + "." + payload, secret)):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        data = json.loads(_unb64(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None
