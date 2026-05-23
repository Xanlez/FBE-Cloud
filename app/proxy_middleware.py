"""Fix request URL behind reverse proxy (nginx, Keenetic, etc.)."""

from urllib.parse import urlparse

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _header(scope: dict, name: bytes) -> str | None:
    for key, value in scope.get("headers", ()):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _split_host_port(host: str, scheme: str) -> tuple[str, int]:
    host = host.strip()
    if not host:
        return "localhost", 1010
    if host.startswith("["):
        if "]" in host:
            name, _, rest = host.partition("]")
            if rest.startswith(":"):
                return name + "]", int(rest[1:])
            return host, 443 if scheme == "https" else 80
    if ":" in host:
        hostname, _, port_s = host.rpartition(":")
        if port_s.isdigit():
            return hostname, int(port_s)
    return host, 443 if scheme == "https" else 80


def _apply_public_url(scope: dict, public_url: str) -> None:
    parsed = urlparse(public_url)
    if not parsed.hostname:
        return
    scope["scheme"] = parsed.scheme or "http"
    scope["server"] = (
        parsed.hostname,
        parsed.port or (443 if scope["scheme"] == "https" else 80),
    )


class FixUpstreamHostMiddleware:
    """
    When the app listens on 127.0.0.1 but the browser uses a public Host,
    Starlette still builds links from scope["server"] → broken CSS and redirects.

    Order: run after ProxyHeadersMiddleware; uses Host if backend is still local.
    """

    def __init__(self, app, public_base_url: str = ""):
        self.app = app
        self.public_base_url = (public_base_url or "").rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.public_base_url:
            _apply_public_url(scope, self.public_base_url)
        else:
            host, _port = scope.get("server", ("127.0.0.1", 1010))
            if host in _LOCAL_HOSTS:
                http_host = _header(scope, b"host")
                if http_host:
                    hostname, port = _split_host_port(http_host, scope.get("scheme", "http"))
                    scope["server"] = (hostname, port)

        await self.app(scope, receive, send)
