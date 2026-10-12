"""SearXNG results are cached through SharedCache: one upstream call serves repeated and cross-worker requests.
Also pins the request MAVE sends to SearXNG and how its JSON is mapped. Needs httpx importable (the upstream call
itself is faked)."""
import asyncio
import importlib.util
import unittest
from unittest import mock

from tests.test_cache import FakeKV

HAVE_HTTPX = importlib.util.find_spec("httpx") is not None

DEFAULT_PAYLOAD = {"results": [{"title": "<b>Hi</b>", "url": "https://a.test/1", "content": "d <i>x</i>"}]}


class _Resp:
    def __init__(self, payload, status_code=200):
        self.payload, self.status_code = payload, status_code

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _fake_client(calls, payload=None, status_code=200):
    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            calls.append((a, k))
            return _Resp(DEFAULT_PAYLOAD if payload is None else payload, status_code)

    return C


@unittest.skipUnless(HAVE_HTTPX, "httpx not installed")
class TestProviderCache(unittest.TestCase):
    def setUp(self):
        from app.core.cache import SharedCache
        from app.search import web

        self.web, self.kv, self.calls = web, FakeKV(), []
        self.cache_a = SharedCache("providers", ttl=300, client=self.kv)  # worker A
        self.cache_b = SharedCache("providers", ttl=300, client=self.kv)  # worker B
        p = mock.patch.dict("os.environ", {"SEARXNG_URL": "http://searxng:8080/", "MAVE_ENV": "development"})
        p.start()
        self.addCleanup(p.stop)
        c = mock.patch.object(web.httpx, "AsyncClient", _fake_client(self.calls))
        c.start()
        self.addCleanup(c.stop)

    def search(self, cache, q="oromia", kind="web", **kw):
        with mock.patch.object(self.web, "_cache", cache):
            return asyncio.run(self.web.web_search(q, kind, **kw))

    def test_second_request_is_served_from_cache(self):
        first = self.search(self.cache_a)
        again = self.search(self.cache_a)
        self.assertEqual((len(self.calls), first, again), (1, again, first))
        self.assertEqual(first[0]["title"], "Hi")  # markup stripped before caching
        self.assertEqual(first[0]["snippet"], "d x")

    def test_other_worker_reuses_the_result_through_redis(self):
        self.search(self.cache_a)
        self.search(self.cache_b)
        self.assertEqual(len(self.calls), 1)

    def test_page_query_and_kind_are_part_of_the_key(self):
        self.search(self.cache_a, offset=0)
        self.search(self.cache_a, offset=20)
        self.search(self.cache_a, q="other")
        self.assertEqual(len(self.calls), 3)

    def test_callers_cannot_corrupt_the_cached_list(self):
        self.search(self.cache_a)[0]["title"] = "MUTATED"
        self.assertEqual(self.search(self.cache_a)[0]["title"], "Hi")


@unittest.skipUnless(HAVE_HTTPX, "httpx not installed")
class TestSearxngRequest(unittest.TestCase):
    """What is sent to SearXNG and how its answer is mapped to MAVE results."""

    def setUp(self):
        from app.core.cache import SharedCache
        from app.search import web

        self.web, self.calls = web, []
        self.cache = SharedCache("providers", ttl=300, client=FakeKV())
        p = mock.patch.dict("os.environ", {"SEARXNG_URL": "http://searxng:8080/", "MAVE_ENV": "development"})
        p.start()
        self.addCleanup(p.stop)

    def run_search(self, payload=None, status_code=200, q="oromia", kind="web", **kw):
        client = mock.patch.object(self.web.httpx, "AsyncClient", _fake_client(self.calls, payload, status_code))
        with client, mock.patch.object(self.web, "_cache", self.cache):
            return asyncio.run(self.web.web_search(q, kind, **kw))

    def sent(self):
        (url,), kwargs = self.calls[-1]
        return url, kwargs["params"]

    def test_json_search_request_goes_to_the_configured_instance(self):
        self.run_search()
        url, params = self.sent()
        self.assertEqual(url, "http://searxng:8080/search")  # trailing slash of the setting is ignored
        self.assertEqual((params["q"], params["format"], params["categories"]), ("oromia", "json", "general"))

    def test_each_result_type_maps_to_a_searxng_category(self):
        for kind, category in (("web", "general"), ("tech", "general"), ("news", "news"), ("images", "images"), ("videos", "videos")):
            self.run_search(q=f"q-{kind}", kind=kind)
            self.assertEqual(self.sent()[1]["categories"], category, kind)
        self.run_search(q="python", kind="tech")
        self.assertEqual(self.sent()[1]["q"], "python technology")

    def test_pages_are_requested_by_number(self):
        for offset, page in ((0, 1), (20, 2), (40, 3)):
            self.run_search(q=f"p{offset}", offset=offset, count=20)
            self.assertEqual(self.sent()[1]["pageno"], page)

    def test_images_use_the_thumbnail_and_fall_back_to_the_image(self):
        payload = {"results": [
            {"title": "a", "url": "https://p.test/a", "img_src": "https://i.test/a.jpg", "thumbnail_src": "https://i.test/a_t.jpg"},
            {"title": "b", "url": "https://p.test/b", "img_src": "https://i.test/b.jpg"},
        ]}
        got = self.run_search(payload, kind="images")
        self.assertEqual([r["thumbnail"] for r in got], ["https://i.test/a_t.jpg", "https://i.test/b.jpg"])
        self.assertEqual(got[0]["url"], "https://p.test/a")  # the link is the page, not the image

    def test_unsafe_or_missing_urls_are_dropped(self):
        payload = {"results": [
            {"title": "js", "url": "javascript:alert(1)"},
            {"title": "none"},
            {"title": "ok", "url": "https://ok.test/", "thumbnail": "data:image/png;base64,AAAA"},
            "not-a-dict",
        ]}
        got = self.run_search(payload)
        self.assertEqual([(r["title"], r["thumbnail"]) for r in got], [("ok", None)])

    def test_result_count_is_capped(self):
        payload = {"results": [{"title": str(i), "url": f"https://a.test/{i}"} for i in range(30)]}
        self.assertEqual(len(self.run_search(payload, count=20)), 20)

    def test_provider_failures_become_provider_errors(self):
        from app.core.errors import ProviderError

        with self.assertRaises(ProviderError):
            self.run_search(status_code=403)  # e.g. the json format is not enabled on the instance
        with self.assertRaises(ProviderError):
            self.run_search(ValueError("not json"), q="bad json")

    def test_not_configured_means_demo_in_development_and_error_in_production(self):
        from app.core.errors import ProviderError

        with mock.patch.dict("os.environ", {"SEARXNG_URL": ""}):
            self.assertTrue(asyncio.run(self.web.web_search("x")))
            self.assertEqual(asyncio.run(self.web.web_search("x", offset=20)), [])
            with mock.patch.dict("os.environ", {"MAVE_ENV": "production"}), self.assertRaises(ProviderError):
                asyncio.run(self.web.web_search("x"))


if __name__ == "__main__":
    unittest.main()
