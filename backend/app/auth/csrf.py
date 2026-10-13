"""Login CSRF protection for /auth/login and /auth/register.

The session cookie is SameSite=Strict, so another site can't use an
existing session; but a cross-site form POST to /auth/login could still
sign the visitor's browser into an account the attacker controls (login
CSRF), and whatever they then save lands in that account. Browsers send
an Origin header on every cross-site POST, so a request whose Origin is
present and not on the CORS_ORIGINS allowlist is refused.

The allowlist is the one CORS already uses: the Vite dev server locally,
the Compose web app (docker-compose.yml), and the site itself when
deployed (infra/hub/lambda.tf; CloudFront forwards Origin). Requests with
no Origin header (API clients: the MCP server, curl, scripts) are
unaffected, as before.
"""

from fastapi import HTTPException, Request, status

from app.core import config


def require_allowed_origin(request: Request) -> None:
    """FastAPI dependency: 403 for a present, unlisted Origin."""
    origin = request.headers.get("origin")
    # Looked up at call time, so tests (and a reload) see the current list.
    if origin is not None and origin not in config.CORS_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site sign-in refused",
        )
