"""Errors shared across layers."""


class ProviderError(Exception):
    """An external provider (web search, AI) is unconfigured, unreachable or returned an error.

    The message is returned to API clients (HTTP 502), so it must never contain keys or upstream text.
    """
