"""Runtime configuration.

Every value is read from the environment *when it is accessed*, not when this module is imported.
This matters because several modules do ``from .config import settings`` at import time: with eager
evaluation, whichever test (or process) imported the app first froze the configuration, so later
changes to MAVE_ADMIN_KEY / MAVE_DATABASE_URL were silently ignored (the admin-stats test failure).
"""
import os
import secrets

_fallback_jwt_secret: str | None = None


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


class Settings:
    @property
    def env(self) -> str:
        return _env("MAVE_ENV", "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def database_url(self) -> str:
        """PostgreSQL connection string. The default only suits local development (see docker-compose.yml)."""
        return _env("MAVE_DATABASE_URL") or "postgresql://mave:mave@localhost:5432/mave"

    @property
    def db_pool_size(self) -> int:
        """Maximum pooled PostgreSQL connections per process."""
        return max(1, _int("MAVE_DB_POOL_SIZE", 10))

    @property
    def jwt_secret(self) -> str:
        # Without MAVE_JWT_SECRET tokens die on every restart. The random fallback is generated once
        # per process (never per access) and is rejected outright in production, see validate().
        global _fallback_jwt_secret
        explicit = _env("MAVE_JWT_SECRET")
        if explicit:
            return explicit
        if _fallback_jwt_secret is None:
            _fallback_jwt_secret = secrets.token_hex(32)
        return _fallback_jwt_secret

    @property
    def admin_key(self) -> str:
        return _env("MAVE_ADMIN_KEY")

    @property
    def searxng_url(self) -> str:
        """Base URL of the SearXNG instance used for web search, without a trailing slash (e.g. http://searxng:8080).
        Empty = not configured."""
        return _env("SEARXNG_URL").strip().rstrip("/")

    @property
    def anthropic_key(self) -> str:
        return _env("ANTHROPIC_API_KEY")

    @property
    def model(self) -> str:
        """Anthropic model name (used when Anthropic is the AI provider)."""
        return _env("MAVE_MODEL", "claude-sonnet-5-5")

    @property
    def xai_key(self) -> str:
        return _env("XAI_API_KEY").strip()

    @property
    def xai_model(self) -> str:
        return _env("MAVE_XAI_MODEL", "grok-4.6").strip() or "grok-4.6"

    @property
    def ai_provider(self) -> str | None:
        """Which provider answers /ai/answer: "xai", "anthropic" or None (not configured).

        MAVE_AI_PROVIDER=xai|anthropic forces one (no silent fallback to the other); anything else means
        "auto": xAI when XAI_API_KEY is set, otherwise Anthropic when ANTHROPIC_API_KEY is set.
        """
        choice = _env("MAVE_AI_PROVIDER", "auto").strip().lower()
        if choice == "xai":
            return "xai" if self.xai_key else None
        if choice == "anthropic":
            return "anthropic" if self.anthropic_key else None
        if self.xai_key:
            return "xai"
        if self.anthropic_key:
            return "anthropic"
        return None

    @property
    def rate_limit_per_min(self) -> int:
        return _int("MAVE_RATE_LIMIT", 90)

    @property
    def redis_url(self) -> str:
        # Optional. With it, rate limits are shared by all workers/replicas; without it each process counts alone.
        return _env("MAVE_REDIS_URL").strip()

    @property
    def trust_proxy(self) -> bool:
        return _env("MAVE_TRUST_PROXY") == "1"

    @property
    def access_ttl(self) -> int:
        # Short-lived access token (seconds); clients renew it with the refresh token.
        return max(60, _int("MAVE_ACCESS_TTL", 900))

    @property
    def refresh_ttl(self) -> int:
        # Sliding lifetime of a refresh token (seconds); a session is also capped at 90 days in auth.py.
        return max(3600, _int("MAVE_REFRESH_TTL", 30 * 86400))

    @property
    def public_url(self) -> str:
        # Public base URL of the web app, used in password-reset / verification e-mail links.
        return _env("MAVE_PUBLIC_URL").strip().rstrip("/")

    @property
    def smtp_host(self) -> str:
        return _env("MAVE_SMTP_HOST").strip()

    @property
    def smtp_port(self) -> int:
        return _int("MAVE_SMTP_PORT", 587)

    @property
    def smtp_user(self) -> str:
        return _env("MAVE_SMTP_USER")

    @property
    def smtp_password(self) -> str:
        return _env("MAVE_SMTP_PASSWORD")

    @property
    def smtp_from(self) -> str:
        return _env("MAVE_SMTP_FROM") or self.smtp_user or "no-reply@localhost"

    @property
    def smtp_starttls(self) -> bool:
        return _env("MAVE_SMTP_STARTTLS", "1") != "0"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in _env("MAVE_CORS_ORIGINS").split(",") if o.strip()]

    @property
    def bot_name(self) -> str:
        # Set MAVE_BOT_URL to the public page describing your crawler; no placeholder URL is shipped.
        url = _env("MAVE_BOT_URL").strip()
        return f"MAVEBot/0.3 (+{url})" if url else "MAVEBot/0.3"

    @property
    def auth_rate_limit_per_min(self) -> int:
        # Stricter limit for login/register/refresh to slow down password guessing.
        return min(_int("MAVE_AUTH_RATE_LIMIT", 10), self.rate_limit_per_min)

    def validate(self) -> list[str]:
        """Problems that make the configuration unsafe for production (startup must fail)."""
        problems = []
        if len(_env("MAVE_JWT_SECRET")) < 32 or _env("MAVE_JWT_SECRET").startswith("change-me"):
            problems.append("MAVE_JWT_SECRET must be set to a random value of at least 32 characters")
        if not _env("MAVE_DATABASE_URL"):
            problems.append("MAVE_DATABASE_URL must point at the production PostgreSQL database")
        key = self.admin_key
        if len(key) < 16 or key.startswith("change-me"):
            problems.append("MAVE_ADMIN_KEY must be set to a random value of at least 16 characters")
        return problems

    def warnings(self) -> list[str]:
        """Non-fatal production gaps."""
        out = []
        if not self.searxng_url:
            out.append("SEARXNG_URL is not set: external web search is unavailable")
        elif not self.searxng_url.lower().startswith(("http://", "https://")):
            out.append("SEARXNG_URL must start with http:// or https://: external web search is unavailable")
        if not self.ai_provider:
            out.append("XAI_API_KEY (or ANTHROPIC_API_KEY) is not set: AI answers are unavailable")
        if not self.smtp_host:
            out.append("MAVE_SMTP_HOST is not set: password-reset and verification e-mails cannot be sent")
        if not self.cors_origins:
            out.append("MAVE_CORS_ORIGINS is empty: browsers on other origins (web app) will be refused")
        if self.is_production and not self.redis_url:
            out.append("MAVE_REDIS_URL is not set: rate limits are counted per process (fine for one worker, too lax for several)")
        return out


settings = Settings()
