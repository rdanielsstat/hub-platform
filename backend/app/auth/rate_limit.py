"""Per-client-IP rate limiting for /auth/login and /auth/register.

In-process and in-memory, so no new dependency and no shared store. The
catch: on Lambda each warm container keeps its own counts, so with N
containers running a client could get up to N times the limit through.
API Gateway stage throttling (infra/hub/apigateway.tf) is the global
backstop; see backend/README.md for both thresholds.
"""

import ipaddress
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import (
    CLIENT_IP_HEADER,
    LOGIN_RATE_LIMIT_PER_MINUTE,
    REGISTER_RATE_LIMIT_PER_MINUTE,
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

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


def client_ip(request: Request, header: str | None = None) -> str:
    """The client IP: from the trusted proxy header when one is
    configured and holds a valid address, else the TCP peer address.
    A malformed header falls back to the peer rather than becoming a
    bucket of its own, so junk values can't mint fresh rate-limit keys.
    header defaults to CLIENT_IP_HEADER, read at call time."""
    if header is None:
        header = CLIENT_IP_HEADER
    if header:
        ip = _ip_from_header(request.headers.get(header, ""))
        if ip is not None:
            return str(ip)
    peer = request.client.host if request.client else ""
    ip = _parse_ip(peer)
    return str(ip) if ip is not None else (peer or "unknown")


def rate_limit_key(request: Request, header: str | None = None) -> str:
    """What the per-IP limits count by: the IPv4 address, or for IPv6
    the /64 network it's in. One IPv6 subscriber usually gets a whole
    /64 and can rotate through its addresses at will, so counting single
    IPv6 addresses would let them dodge the limit."""
    address = client_ip(request, header)
    ip = _parse_ip(address)
    if isinstance(ip, ipaddress.IPv6Address):
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return address


login_rate_limiter = SlidingWindowRateLimiter(LOGIN_RATE_LIMIT_PER_MINUTE)
register_rate_limiter = SlidingWindowRateLimiter(REGISTER_RATE_LIMIT_PER_MINUTE)


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
