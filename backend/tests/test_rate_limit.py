import pytest
from starlette.requests import Request

from app.auth import rate_limit
from app.auth.rate_limit import SlidingWindowRateLimiter, client_ip, rate_limit_key
from tests.conftest import TEST_PASSWORD


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks():
    limiter = SlidingWindowRateLimiter(3, clock=FakeClock())

    assert [limiter.hit("ip") for _ in range(3)] == [None, None, None]
    assert limiter.hit("ip") == pytest.approx(60.0)


def test_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(2, clock=clock)
    limiter.hit("ip")
    clock.now += 30
    limiter.hit("ip")

    clock.now += 29
    assert limiter.hit("ip") == pytest.approx(1.0)
    clock.now += 1
    assert limiter.hit("ip") is None  # the first hit has aged out


def test_blocked_attempts_do_not_extend_the_lockout():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(1, clock=clock)
    limiter.hit("ip")
    for _ in range(10):
        clock.now += 5
        limiter.hit("ip")

    clock.now += 10  # 60s after the only recorded hit
    assert limiter.hit("ip") is None


def test_keys_are_counted_separately():
    limiter = SlidingWindowRateLimiter(1, clock=FakeClock())

    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("a") is not None


def test_zero_disables_the_limit():
    limiter = SlidingWindowRateLimiter(0, clock=FakeClock())

    assert all(limiter.hit("ip") is None for _ in range(100))


def _request(headers: dict[str, str], peer: str = "10.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("203.0.113.7:443", "203.0.113.7"),
        ("2001:db8::1:443", "2001:db8::1"),
        ("203.0.113.7", "203.0.113.7"),
    ],
)
def test_client_ip_reads_the_trusted_header_and_strips_the_port(value, expected):
    request = _request({"CloudFront-Viewer-Address": value})

    assert client_ip(request, header="CloudFront-Viewer-Address") == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2001:db8::1", "2001:db8::1"),  # bare IPv6, no port
        ("::1", "::1"),
        ("2001:db8:0:0:0:0:0:7", "2001:db8::7"),  # full form, normalised
        ("[2001:db8::1]:443", "2001:db8::1"),  # bracketed with port
        ("[2001:db8::1]", "2001:db8::1"),
        ("::ffff:203.0.113.7", "203.0.113.7"),  # IPv4-mapped
        ("::ffff:203.0.113.7:443", "203.0.113.7"),
        (" 203.0.113.7:443 ", "203.0.113.7"),
    ],
)
def test_client_ip_handles_bare_bracketed_and_mapped_addresses(value, expected):
    request = _request({"CloudFront-Viewer-Address": value})

    assert client_ip(request, header="CloudFront-Viewer-Address") == expected


@pytest.mark.parametrize(
    "value",
    ["not-an-ip", "garbage:443", "[2001:db8::1", "999.1.1.1:443", ":443", "203.0.113.7:99999"],
)
def test_a_malformed_header_falls_back_to_the_peer_address(value):
    """Junk can't mint a fresh rate-limit bucket per request."""
    request = _request({"CloudFront-Viewer-Address": value})

    assert client_ip(request, header="CloudFront-Viewer-Address") == "10.0.0.1"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("203.0.113.7:443", "203.0.113.7"),
        ("2001:db8:aaaa:bbbb:1:2:3:4:443", "2001:db8:aaaa:bbbb::/64"),
        ("2001:db8:aaaa:bbbb::ffff:443", "2001:db8:aaaa:bbbb::/64"),
        ("::ffff:203.0.113.7:443", "203.0.113.7"),
    ],
)
def test_rate_limit_key_groups_ipv6_by_64(value, expected):
    request = _request({"CloudFront-Viewer-Address": value})

    assert rate_limit_key(request, header="CloudFront-Viewer-Address") == expected


def test_addresses_in_one_ipv6_64_share_a_login_bucket(client, monkeypatch):
    """Rotating through addresses in one /64 doesn't reset the count."""
    monkeypatch.setattr(rate_limit, "CLIENT_IP_HEADER", "CloudFront-Viewer-Address")
    monkeypatch.setattr(rate_limit, "login_rate_limiter", SlidingWindowRateLimiter(2))
    form = {"username": "nobody@example.com", "password": "wrong-password"}

    def attempt(addr: str) -> int:
        return client.post(
            "/auth/login", data=form, headers={"CloudFront-Viewer-Address": addr}
        ).status_code

    assert attempt("2001:db8:1:2::a:443") == 401
    assert attempt("2001:db8:1:2::b:443") == 401
    assert attempt("2001:db8:1:2::c:443") == 429
    # A different /64 is a different client.
    assert attempt("2001:db8:1:3::a:443") == 401


def test_client_ip_falls_back_to_the_peer_address():
    assert client_ip(_request({}), header="CloudFront-Viewer-Address") == "10.0.0.1"


def test_client_ip_ignores_the_header_unless_configured():
    request = _request({"CloudFront-Viewer-Address": "203.0.113.7:443"})

    assert client_ip(request, header="") == "10.0.0.1"


@pytest.fixture()
def login_limit_of_five(monkeypatch):
    monkeypatch.setattr(rate_limit, "login_rate_limiter", SlidingWindowRateLimiter(5))


def test_login_returns_429_after_five_attempts_per_minute(client, login_limit_of_five):
    client.post(
        "/auth/register",
        json={"email": "limited@example.com", "password": TEST_PASSWORD},
    )
    form = {"username": "limited@example.com", "password": "wrong-password"}

    statuses = [client.post("/auth/login", data=form).status_code for _ in range(5)]
    blocked = client.post("/auth/login", data=form)

    assert statuses == [401] * 5
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many login attempts. Try again in a minute."}
    assert 1 <= int(blocked.headers["retry-after"]) <= 60

    # Even the right password is refused until the window passes.
    right = {"username": "limited@example.com", "password": TEST_PASSWORD}
    assert client.post("/auth/login", data=right).status_code == 429


def test_the_login_limit_does_not_apply_to_register(client, login_limit_of_five):
    for i in range(7):
        res = client.post(
            "/auth/register",
            json={"email": f"many-{i}@example.com", "password": TEST_PASSWORD},
        )
        assert res.status_code == 201


@pytest.fixture()
def register_limit_of_three(monkeypatch):
    monkeypatch.setattr(
        rate_limit, "register_rate_limiter", SlidingWindowRateLimiter(3)
    )


def test_register_returns_429_after_three_attempts_per_minute(
    client, register_limit_of_three
):
    statuses = [
        client.post(
            "/auth/register",
            json={"email": f"burst-{i}@example.com", "password": TEST_PASSWORD},
        ).status_code
        for i in range(3)
    ]
    blocked = client.post(
        "/auth/register",
        json={"email": "burst-3@example.com", "password": TEST_PASSWORD},
    )

    assert statuses == [201, 201, 201]
    assert blocked.status_code == 429
    assert blocked.json() == {
        "detail": "Too many sign-up attempts. Try again in a minute."
    }
    assert 1 <= int(blocked.headers["retry-after"]) <= 60


def test_rejected_registrations_count_toward_the_limit(
    client, register_limit_of_three
):
    """Duplicate (409) and invalid (422) attempts count too, so probing
    which emails exist, or hammering argon2, is limited the same way."""
    first = {"email": "dupe@example.com", "password": TEST_PASSWORD}
    assert client.post("/auth/register", json=first).status_code == 201
    assert client.post("/auth/register", json=first).status_code == 409
    assert client.post("/auth/register", json={"email": "bad"}).status_code == 422

    res = client.post(
        "/auth/register", json={"email": "fresh@example.com", "password": TEST_PASSWORD}
    )
    assert res.status_code == 429


def test_register_and_login_limits_are_counted_separately(
    client, register_limit_of_three, login_limit_of_five
):
    for i in range(3):
        client.post(
            "/auth/register",
            json={"email": f"sep-{i}@example.com", "password": TEST_PASSWORD},
        )
    assert (
        client.post(
            "/auth/register",
            json={"email": "sep-x@example.com", "password": TEST_PASSWORD},
        ).status_code
        == 429
    )

    # The register limit being spent doesn't touch login.
    login = client.post(
        "/auth/login", data={"username": "sep-0@example.com", "password": TEST_PASSWORD}
    )
    assert login.status_code == 200

