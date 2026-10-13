"""L6: the live test registers a throwaway account, so it refuses to run
against anything but a local backend (tests/live_guard.py)."""

import pytest

from tests.live_guard import require_local_api


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "http://hub.localhost:8000",
    ],
)
def test_local_backends_are_allowed(url):
    require_local_api(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://hub.dnls.dev/api",
        "https://hub-dev.dnls.dev/api",
        "http://localhost.evil.com",
        "http://192.168.1.20:8000",
        "not a url",
    ],
)
def test_anything_else_is_refused(url):
    with pytest.raises(RuntimeError, match="local backend"):
        require_local_api(url)


def test_the_live_test_calls_the_guard():
    import inspect

    from tests import test_live_api

    assert "require_local_api(API_URL)" in inspect.getsource(test_live_api)
