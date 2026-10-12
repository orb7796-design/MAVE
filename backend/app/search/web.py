"""External web search provider: SearXNG (self-hosted metasearch; web / news / images / videos). Results are cached
through ``SharedCache`` (public data, safe to share between workers). Without ``SEARXNG_URL`` it serves demo data in
development and raises ``ProviderError`` in production.

SearXNG must have the JSON output format enabled (``search.formats: [html, json]`` in its settings.yml, see
``ops/searxng/settings.yml``); otherwise it answers 403 and this module reports a provider error."""
import re

import httpx

from ..core.cache import build_cache
from ..core.config import settings
from ..core.errors import ProviderError

# MAVE result type -> SearXNG category. "tech" is a plain web search with a topical suffix (see web_search).
SEARXNG_CATEGORIES = {
    "web": "general",
    "tech": "general",
    "news": "news",
    "images": "images",
    "videos": "videos",
}
TAG = re.compile(r"<[^>]+>")
_cache = build_cache("providers", ttl=300, maxsize=512)  # public search results: safe to share between workers


def demo_results(q: str, kind: str) -> list[dict]:
    return [
        {
            "title": f"{q} - demo result {i}",
            "url": f"https://example.com/{kind}/{i}",
            "snippet": "Demo data. Set SEARXNG_URL on the server to get real web results.",
            "thumbnail": f"https://picsum.photos/seed/{kind}{i}/300/300",
            "source": "web",
        }
        for i in range(1, 9)
    ]


def _http_url(value) -> str | None:
    """Only http(s) URLs are passed on to clients (SearXNG engines can return anything)."""
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return value
    return None


def _item(x: dict, kind: str) -> dict | None:
    url = _http_url(x.get("url"))
    if not url:
        return None
    thumb = x.get("thumbnail_src") or x.get("thumbnail") or (x.get("img_src") if kind == "images" else None)
    return {
        "title": TAG.sub("", x.get("title") or ""),
        "url": url,
        "snippet": TAG.sub("", x.get("content") or ""),
        "thumbnail": _http_url(thumb),
        "source": "web",
    }


async def web_search(q: str, kind: str = "web", count: int = 20, offset: int = 0) -> list[dict]:
    base = settings.searxng_url
    if not base:
        if settings.is_production:  # demo data must never be served as if it were real results
            raise ProviderError("search provider is not configured")
        return demo_results(q, kind) if offset == 0 else []
    key = (q, kind, count, offset)
    hit = await _cache.aget(key)
    if hit is not None:
        return hit
    query = f"{q} technology" if kind == "tech" else q
    params = {
        "q": query,
        "format": "json",
        "categories": SEARXNG_CATEGORIES[kind],
        "pageno": max(1, offset // max(1, count) + 1),  # SearXNG pages by number, not by offset
        "safesearch": 1,  # moderate
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{base}/search", params=params, headers={"Accept": "application/json"})
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        raise ProviderError(f"search provider unreachable: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise ProviderError(f"search provider error {r.status_code}")
    try:
        data = r.json()
        raw = data.get("results", []) if isinstance(data, dict) else []
    except ValueError as e:
        raise ProviderError("search provider returned invalid JSON") from e
    items = [it for it in (_item(x, kind) for x in raw if isinstance(x, dict)) if it]
    items = items[:count]
    await _cache.aset(key, items)
    return items
