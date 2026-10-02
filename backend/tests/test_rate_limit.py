import pytest
from starlette.requests import Request

from app.auth import rate_limit
from app.auth.rate_limit import SlidingWindowRateLimiter, client_ip
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


def test_register_is_not_rate_limited(client, login_limit_of_five):
    for i in range(7):
        res = client.post(
            "/auth/register",
            json={"email": f"many-{i}@example.com", "password": TEST_PASSWORD},
        )
        assert res.status_code == 201
