"""Per-client-IP rate limiting for /auth/login, /auth/register and
/client-errors.

In-process and in-memory, so no new dependency and no shared store. The
catch: on Lambda each warm container keeps its own counts, so with N
containers running a client could get up to N times the limit through.
API Gateway stage throttling (infra/hub/apigateway.tf) is the global
backstop; see backend/README.md for both thresholds, and
security/RATE_LIMITING.md for the full picture.
"""

import ipaddress
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import (
    CLIENT_ERROR_RATE_LIMIT_PER_MINUTE,
    CLIENT_IP_HEADER,
    LOGIN_RATE_LIMIT_PER_MINUTE,
    REGISTER_RATE_LIMIT_PER_MINUTE,
    TRUSTED_PROXY_IPS,
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

FORWARDED_FOR_HEADER = "X-Forwarded-For"

# Parsed once; config.parse_trusted_proxies() already validated them.
TRUSTED_PROXY_NETWORKS: tuple[IPNetwork, ...] = tuple(
    ipaddress.ip_network(n) for n in TRUSTED_PROXY_IPS
)

# Past this many tracked clients, prune the ones with no recent attempts
# so a spray of distinct IPs can't grow memory without bound.
_PRUNE_THRESHOLD = 10_000


class SlidingWindowRateLimiter:
    """At most `limit` hits per key in any `window_seconds` window. A
    limit of 0 or less disables it."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record an attempt for key. None if it's allowed, otherwise
        the seconds until the oldest attempt in the window expires (the
        attempt itself is not recorded)."""
        if self.limit <= 0:
            return None
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            if len(self._hits) > _PRUNE_THRESHOLD:
                self._prune(cutoff)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] - cutoff
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, cutoff: float) -> None:
        stale = [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]


def _parse_ip(text: str) -> IPAddress | None:
    try:
        ip = ipaddress.ip_address(text.strip())
    except ValueError:
        return None
    # ::ffff:203.0.113.7 is an IPv4 client seen over IPv6: count it as
    # that IPv4 address, not as a separate IPv6 one.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _ip_from_header(value: str) -> IPAddress | None:
    """The address in a proxy header value, with or without a port.

    CloudFront-Viewer-Address is "ip:port", and IPv6 is unbracketed
    ("2001:db8::1:443"), so the port is the text after the last colon.
    That is tried first, because a bare IPv6 address can also end in what
    looks like a port group. Bare addresses ("203.0.113.7",
    "2001:db8::1") and bracketed IPv6 ("[2001:db8::1]:443") are accepted
    too. Anything that isn't an address gives None."""
    value = value.strip()
    if value.startswith("["):
        host, sep, _rest = value[1:].partition("]")
        return _parse_ip(host) if sep else None
    host, sep, port = value.rpartition(":")
    # Only a numeric suffix in port range is a port: in a bare
    # "::ffff:203.0.113.7" the text before the last colon ("::ffff") is
    # itself a valid address, so the suffix's shape has to decide.
    if sep and port.isdigit() and int(port) <= 65535:
        ip = _parse_ip(host)
        if ip is not None:
            return ip
    return _parse_ip(value)


def _is_trusted(ip: IPAddress, trusted: tuple[IPNetwork, ...]) -> bool:
    return any(ip.version == net.version and ip in net for net in trusted)


def _client_from_forwarded_for(
    value: str, hop: IPAddress, trusted: tuple[IPNetwork, ...]
) -> IPAddress | None:
    """The client in an X-Forwarded-For chain, given that `hop` (a trusted
    proxy) is the last machine we can vouch for.

    Each proxy appends the address it received the request from, so the
    list reads client, proxy1, proxy2, ... and only the right-hand end is
    trustworthy: anything further left may have been sent by the client.
    So: drop whatever was appended after `hop` itself (behind Cloudflare,
    CloudFront and API Gateway can add their own entries), then walk right
    to left past trusted proxies; the first untrusted address is the
    client. A malformed entry stops the walk (None: use `hop`) rather than
    trusting anything to its left."""
    entries = [_ip_from_header(part) for part in value.split(",") if part.strip()]
    for i in range(len(entries) - 1, -1, -1):
        if entries[i] == hop:
            entries = entries[:i]
            break
    for ip in reversed(entries):
        if ip is None:
            return None
        if not _is_trusted(ip, trusted):
            return ip
    return None


def client_ip(
    request: Request,
    header: str | None = None,
    trusted: tuple[IPNetwork, ...] | None = None,
) -> str:
    """The client IP.

    First the nearest hop we can see: the address in the configured proxy
    header (CLIENT_IP_HEADER, CloudFront-Viewer-Address when deployed),
    else the TCP peer. A malformed header falls back to the peer rather
    than becoming a bucket of its own, so junk values can't mint fresh
    rate-limit keys.

    Then, only if that hop is a trusted proxy (TRUSTED_PROXY_IPS, e.g.
    Cloudflare's ranges), the client from X-Forwarded-For. With no trusted
    proxies (the default), or a hop outside them, X-Forwarded-For is
    ignored entirely, so a client can't pick its own address by sending one.

    header and trusted default to the configured values, read at call
    time so tests can swap them."""
    if header is None:
        header = CLIENT_IP_HEADER
    if trusted is None:
        trusted = TRUSTED_PROXY_NETWORKS
    hop = _ip_from_header(request.headers.get(header, "")) if header else None
    if hop is None:
        peer = request.client.host if request.client else ""
        hop = _parse_ip(peer)
        if hop is None:
            return peer or "unknown"
    if trusted and _is_trusted(hop, trusted):
        forwarded = _client_from_forwarded_for(
            request.headers.get(FORWARDED_FOR_HEADER, ""), hop, trusted
        )
        if forwarded is not None:
            return str(forwarded)
    return str(hop)


def rate_limit_key(
    request: Request,
    header: str | None = None,
    trusted: tuple[IPNetwork, ...] | None = None,
) -> str:
    """What the per-IP limits count by: the IPv4 address, or for IPv6
    the /64 network it's in. One IPv6 subscriber usually gets a whole
    /64 and can rotate through its addresses at will, so counting single
    IPv6 addresses would let them dodge the limit."""
    address = client_ip(request, header, trusted)
    ip = _parse_ip(address)
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return address


login_rate_limiter = SlidingWindowRateLimiter(LOGIN_RATE_LIMIT_PER_MINUTE)
register_rate_limiter = SlidingWindowRateLimiter(REGISTER_RATE_LIMIT_PER_MINUTE)
client_error_rate_limiter = SlidingWindowRateLimiter(CLIENT_ERROR_RATE_LIMIT_PER_MINUTE)


def _enforce(limiter: SlidingWindowRateLimiter, request: Request, what: str) -> None:
    retry_after = limiter.hit(rate_limit_key(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many {what}. Try again in a minute.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )


def limit_login_attempts(request: Request) -> None:
    """FastAPI dependency for /auth/login: 429 with Retry-After once a
    client IP is over the limit."""
    # Looked up at call time, not bound at import, so tests can swap it.
    _enforce(login_rate_limiter, request, "login attempts")


def limit_register_attempts(request: Request) -> None:
    """FastAPI dependency for /auth/register, same behaviour with its
    own, separate count."""
    _enforce(register_rate_limiter, request, "sign-up attempts")


def limit_client_error_reports(request: Request) -> None:
    """FastAPI dependency for /client-errors, with its own count."""
    _enforce(client_error_rate_limiter, request, "error reports")
