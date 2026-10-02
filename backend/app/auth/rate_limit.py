"""Per-client-IP rate limiting for /auth/login.

In-process and in-memory, so no new dependency and no shared store. The
catch: on Lambda each warm container keeps its own counts, so with N
containers running a client could get up to N times the limit through.
API Gateway stage throttling (infra/hub/apigateway.tf) is the global
backstop; see backend/README.md for both thresholds.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import CLIENT_IP_HEADER, LOGIN_RATE_LIMIT_PER_MINUTE

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


def client_ip(request: Request, header: str = CLIENT_IP_HEADER) -> str:
    """The client IP for rate limiting: from the trusted proxy header
    when one is configured and present, else the TCP peer address.
    CloudFront-Viewer-Address is "ip:port" (IPv6 unbracketed, e.g.
    "2001:db8::1:443"), so the port is the text after the last colon."""
    if header:
        value = request.headers.get(header, "").strip()
        if value:
            ip, sep, _port = value.rpartition(":")
            return ip if sep else value
    return request.client.host if request.client else "unknown"


login_rate_limiter = SlidingWindowRateLimiter(LOGIN_RATE_LIMIT_PER_MINUTE)


def limit_login_attempts(request: Request) -> None:
    """FastAPI dependency for /auth/login: 429 with Retry-After once a
    client IP is over the limit."""
    retry_after = login_rate_limiter.hit(client_ip(request))
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in a minute.",
            headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
        )
