"""Reject requests that didn't come through CloudFront.

API Gateway's default execute-api URL is public. A request sent there
directly skips CloudFront, so it could set CloudFront-Viewer-Address to
anything and dodge the per-IP login rate limit. CloudFront adds a shared
secret header (X-Origin-Verify, see infra/hub/frontend.tf) to everything
it forwards; this middleware answers 403 to any request without the
right value, before routing, auth or the rate limit run.

On only when deployed with USE_SSM (app/main.py passes the secret from
config.get_origin_verify_secret(), None locally). Pure ASGI rather than
BaseHTTPMiddleware, so it adds no per-request task overhead.
"""

import hmac
import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import ORIGIN_VERIFY_HEADER

logger = logging.getLogger("app.security")

_HEADER_KEY = ORIGIN_VERIFY_HEADER.lower().encode("latin-1")
_FORBIDDEN_BODY = json.dumps({"detail": "Forbidden"}).encode()


class OriginVerifyMiddleware:
    def __init__(self, app: ASGIApp, secret: str | None) -> None:
        self.app = app
        self._secret = secret.encode("latin-1") if secret else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._secret is None or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sent = next(
            (value for key, value in scope["headers"] if key == _HEADER_KEY), None
        )
        # Constant-time compare, so response timing can't leak the secret.
        if sent is not None and hmac.compare_digest(sent, self._secret):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        # Never logs the header value itself, only that it was wrong.
        logger.warning(
            "origin_verify_rejected method=%s path=%s source_ip=%s reason=%s",
            scope.get("method"),
            scope.get("path"),
            client[0] if client else "unknown",
            "missing" if sent is None else "mismatch",
        )
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_FORBIDDEN_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _FORBIDDEN_BODY})
