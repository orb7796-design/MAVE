"""MAVE crawler package (public API kept compatible with the old single-file app/crawler.py)."""
from .crawler import Crawler
from .fetch import MAX_BYTES, fetch_raw, fetch_url
from .parser import BAD_EXT, SKIP_TAGS, PageParser, normalize_url, site_key
from .robots import RobotsCache
from .scheduler import enqueue_due, next_interval
from .sitemap import SitemapEntry, discover_sitemap_urls, parse_sitemap

__all__ = [
    "Crawler", "PageParser", "normalize_url", "site_key", "fetch_url", "fetch_raw", "RobotsCache",
    "parse_sitemap", "discover_sitemap_urls", "SitemapEntry", "enqueue_due", "next_interval",
    "BAD_EXT", "SKIP_TAGS", "MAX_BYTES",
]
