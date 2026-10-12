"""SSRF protection for everything that fetches user- or web-supplied URLs (crawler, robots.txt).

Layers:
1. ``check_url``       - scheme / credentials / port / hostname policy, then resolves the name and rejects
                         the URL if ANY resolved address is not publicly routable (loopback, RFC1918,
                         link-local incl. the 169.254.169.254 cloud-metadata address, CGNAT, multicast,
                         reserved, and IPv6 forms that embed an IPv4 address).
2. Guarded sockets     - the TCP connection itself re-resolves and re-validates the address it connects to,
                         so a DNS answer that changes between the check and the connect (DNS rebinding)
                         is still refused.
3. Guarded redirects   - every redirect hop goes through ``check_url`` again; at most 5 hops.
Proxies from the environment are deliberately ignored, otherwise requests would bypass the checks.
"""
import http.client
import ipaddress
import socket
import urllib.request
from urllib.parse import urljoin, urlsplit

ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal", "instance-data"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".corp", ".intranet")


class BlockedURL(ValueError):
    """The URL points somewhere the crawler must never connect to."""


def _unwrap(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Return the embedded IPv4 address for IPv6 forms that tunnel/translate to IPv4."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return ip.ipv4_mapped
        if ip.sixtofour:
            return ip.sixtofour
        if ip.teredo:
            return ip.teredo[1]
        if ip in ipaddress.ip_network("64:ff9b::/96"):  # NAT64
            return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def is_public_ip(value: str) -> bool:
    try:
        ip = _unwrap(ipaddress.ip_address(value.split("%", 1)[0]))
    except ValueError:
        return False
    return bool(ip.is_global) and not ip.is_multicast


def resolve_public(host: str, port: int) -> list[str]:
    """Resolve ``host`` and return its addresses, raising BlockedURL if any is non-public."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise BlockedURL(f"cannot resolve host: {host}") from e
    addrs = []
    for info in infos:
        addr = info[4][0]
        if not is_public_ip(addr):
            raise BlockedURL(f"host {host} resolves to non-public address {addr}")
        if addr not in addrs:
            addrs.append(addr)
    if not addrs:
        raise BlockedURL(f"host {host} has no addresses")
    return addrs


def check_url(url: str) -> str:
    """Validate ``url`` for outbound fetching. Returns it unchanged or raises BlockedURL."""
    try:
        p = urlsplit(url.strip())
        port = p.port
    except ValueError as e:
        raise BlockedURL("malformed URL") from e
    if p.scheme not in ("http", "https"):
        raise BlockedURL(f"scheme not allowed: {p.scheme or 'none'}")
    if p.username is not None or p.password is not None or "@" in p.netloc:
        raise BlockedURL("credentials in URL are not allowed")
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        raise BlockedURL("missing host")
    if port is not None and port not in ALLOWED_PORTS:
        raise BlockedURL(f"port not allowed: {port}")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise BlockedURL(f"host not allowed: {host}")
    resolve_public(host, port or (443 if p.scheme == "https" else 80))
    return url


def _guarded_socket(host: str, port: int, timeout, source_address) -> socket.socket:
    last: Exception | None = None
    for addr in resolve_public(host, port):  # validated again at connect time
        try:
            sock = socket.create_connection((addr, port), timeout, source_address)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return sock
        except OSError as e:
            last = e
    raise last or OSError(f"could not connect to {host}")


class _GuardedHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = _guarded_socket(self.host, self.port, self.timeout, self.source_address)


class _GuardedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        sock = _guarded_socket(self.host, self.port, self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_GuardedHTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_GuardedHTTPSConnection, req, context=self._context)


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)  # always validate (and follow) the absolute form
        check_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _HTTPHandler(), _HTTPSHandler(), _GuardedRedirect()
)


def safe_urlopen(req: urllib.request.Request | str, timeout: float = 10.0):
    """Drop-in replacement for ``urllib.request.urlopen`` that enforces the SSRF policy."""
    url = req if isinstance(req, str) else req.full_url
    check_url(url)
    return _OPENER.open(req, timeout=timeout)
