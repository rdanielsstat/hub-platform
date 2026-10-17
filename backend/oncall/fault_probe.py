"""Proof that project creation works after a dev rollback.

GET /api/health passes even while POST /projects answers 500 (a fault in
the journey, FAULT_INJECT_5XX in the drill), so rollback-dev.yml also
runs this probe: sign in as dev's seeded demo account, create a project
with a unique name, then delete it again.

Exit codes:

    0  POST /projects answered 2xx
    1  POST /projects (or the sign-in) answered 5xx on every attempt
    2  the probe couldn't run: missing settings, a 4xx, or no answer

Anything but 0 fails the rollback. The probe retries a 5xx a few times,
so a cold Lambda or Neon resuming after idle doesn't count as the fault.
It prints status codes only: never the password, the token or a
response body.

Run from backend/ by .github/workflows/rollback-dev.yml as
`python -m oncall.fault_probe`, configured by environment variables:

    PROBE_API_URL        the API base URL, e.g. https://hub-dev.dnls.dev/api
    DEMO_PASSWORDS       the DEMO_PASSWORDS secret, JSON keyed by environment
    PROBE_ENVIRONMENT    which entry to use (default dev)
    PROBE_EMAIL          the account (default demo@hub.dev, app/db/seed.py)
    PROBE_ATTEMPTS       tries before a 5xx counts (default 3)
    PROBE_RETRY_DELAY_S  seconds between tries (default 10)

Standard library only, like the rest of oncall/.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

DEFAULT_EMAIL = "demo@hub.dev"
_TIMEOUT_S = 30

OK, FAULT, CANNOT_RUN = 0, 1, 2


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def json(self) -> dict:
        try:
            data = json.loads(self.body or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}


def _request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    urlopen: Callable[..., object] = urllib.request.urlopen,
) -> _Response | None:
    req = urllib.request.Request(
        url, data=data, method=method, headers=dict(headers or {})
    )
    try:
        with urlopen(req, timeout=_TIMEOUT_S) as res:  # type: ignore[attr-defined]
            return _Response(res.status, res.read())
    except urllib.error.HTTPError as exc:
        return _Response(exc.code, exc.read() if exc.fp else b"")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def probe_name() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"on-call probe {stamp} {uuid.uuid4().hex[:8]}"


def run(
    api_url: str,
    email: str,
    password: str,
    *,
    attempts: int = 3,
    retry_delay_s: float = 10,
    urlopen: Callable[..., object] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    base = api_url.rstrip("/")
    parts = urllib.parse.urlsplit(base)
    # /auth/login refuses a request whose Origin isn't the site's (login
    # CSRF, app/auth/csrf.py).
    origin = f"{parts.scheme}://{parts.netloc}"

    last = None
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            sleep(retry_delay_s)
        login = _request(
            "POST",
            f"{base}/auth/login",
            data=urllib.parse.urlencode(
                {"username": email, "password": password}
            ).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": origin,
            },
            urlopen=urlopen,
        )
        if login is None:
            print(f"probe {attempt}/{attempts}: sign-in got no answer")
            last = None
            continue
        print(f"probe {attempt}/{attempts}: POST /auth/login {login.status}")
        if login.status >= 500:
            last = FAULT
            continue
        token = login.json().get("access_token")
        if login.status != 200 or not isinstance(token, str) or not token:
            return CANNOT_RUN
        auth = {"Authorization": f"Bearer {token}", "Origin": origin}

        created = _request(
            "POST",
            f"{base}/projects",
            data=json.dumps({"name": probe_name()}).encode(),
            headers={**auth, "Content-Type": "application/json"},
            urlopen=urlopen,
        )
        if created is None:
            print(f"probe {attempt}/{attempts}: POST /projects got no answer")
            last = None
            continue
        print(f"probe {attempt}/{attempts}: POST /projects {created.status}")
        if 200 <= created.status < 300:
            project_id = created.json().get("id")
            if isinstance(project_id, str) and project_id:
                deleted = _request(
                    "DELETE",
                    f"{base}/projects/{urllib.parse.quote(project_id, safe='')}",
                    headers=auth,
                    urlopen=urlopen,
                )
                status = deleted.status if deleted else "no answer"
                print(f"probe: DELETE /projects/<probe> {status}")
            return OK
        if created.status >= 500:
            last = FAULT
            continue
        return CANNOT_RUN
    return FAULT if last == FAULT else CANNOT_RUN


def main(
    env: Mapping[str, str] = os.environ,
    urlopen: Callable[..., object] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    api_url = env.get("PROBE_API_URL", "").strip()
    environment = env.get("PROBE_ENVIRONMENT", "dev").strip() or "dev"
    try:
        passwords = json.loads(env.get("DEMO_PASSWORDS", "") or "{}")
    except ValueError:
        passwords = {}
    password = passwords.get(environment) if isinstance(passwords, dict) else None
    if not api_url or not isinstance(password, str) or not password:
        print(
            "::error title=Fault probe::PROBE_API_URL, or the DEMO_PASSWORDS "
            f"entry for {environment}, is missing"
        )
        return CANNOT_RUN
    code = run(
        api_url,
        env.get("PROBE_EMAIL", "").strip() or DEFAULT_EMAIL,
        password,
        attempts=max(1, int(env.get("PROBE_ATTEMPTS", "3"))),
        retry_delay_s=float(env.get("PROBE_RETRY_DELAY_S", "10")),
        urlopen=urlopen,
        sleep=sleep,
    )
    if code == FAULT:
        print(
            "::error title=Fault probe::POST /projects still answers 5xx after the rollback"
        )
    elif code == CANNOT_RUN:
        print(
            "::error title=Fault probe::the probe couldn't create a project (see the status codes above)"
        )
    else:
        print("Fault probe: POST /projects works")
    return code


if __name__ == "__main__":
    sys.exit(main())
