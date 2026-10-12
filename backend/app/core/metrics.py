"""Tiny in-process Prometheus-style metrics (requests, errors, latency). No dependency, process-local.

Behind several workers every worker has its own counters; Prometheus sums them per scrape target. Labels are
bounded (method + route template + status class) so the table can never grow with user input.
"""
import threading
from collections import defaultdict

_lock = threading.Lock()
_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_latency_sum: dict[tuple[str, str], float] = defaultdict(float)
_latency_count: dict[tuple[str, str], int] = defaultdict(int)
_MAX_SERIES = 2000


def observe(method: str, route: str, status: int, seconds: float) -> None:
    key = (method, route[:80], f"{status // 100}xx")
    with _lock:
        if key not in _requests and len(_requests) >= _MAX_SERIES:
            key = (method, "other", key[2])
        _requests[key] += 1
        lk = (method, key[1])
        _latency_sum[lk] += seconds
        _latency_count[lk] += 1


def reset() -> None:
    with _lock:
        _requests.clear()
        _latency_sum.clear()
        _latency_count.clear()


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render(extra_gauges: dict[str, float] | None = None) -> str:
    lines = [
        "# HELP mave_http_requests_total HTTP requests by method, route template and status class.",
        "# TYPE mave_http_requests_total counter",
    ]
    with _lock:
        for (m, r, c), n in sorted(_requests.items()):
            lines.append(f'mave_http_requests_total{{method="{_esc(m)}",route="{_esc(r)}",status="{c}"}} {n}')
        lines += [
            "# HELP mave_http_request_seconds Request latency (sum and count).",
            "# TYPE mave_http_request_seconds summary",
        ]
        for (m, r), total in sorted(_latency_sum.items()):
            lines.append(f'mave_http_request_seconds_sum{{method="{_esc(m)}",route="{_esc(r)}"}} {total:.6f}')
            lines.append(f'mave_http_request_seconds_count{{method="{_esc(m)}",route="{_esc(r)}"}} {_latency_count[(m, r)]}')
    for name, value in sorted((extra_gauges or {}).items()):
        lines += [f"# TYPE {name} gauge", f"{name} {value}"]
    return "\n".join(lines) + "\n"
