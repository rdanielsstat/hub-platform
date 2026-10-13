"""Keeps the live test (test_live_api.py) off real deployments: it
registers a throwaway account on whatever API it's pointed at, which on
dev or prod would leave junk accounts counted against the account cap."""

import ipaddress
from urllib.parse import urlsplit


def require_local_api(url: str) -> None:
    """Raise unless url is a local backend (localhost, *.localhost, or a
    loopback address), such as the Compose stack or uvicorn."""
    host = (urlsplit(url).hostname or "").lower()
    local = host == "localhost" or host.endswith(".localhost")
    if not local:
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
    if not local:
        raise RuntimeError(
            f"The live MCP test only runs against a local backend, not {url!r}: "
            "it registers a throwaway account. Start one with `make docker-up` "
            "and leave HUB_API_URL at http://localhost:8000."
        )
