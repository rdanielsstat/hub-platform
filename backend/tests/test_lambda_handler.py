import importlib
import json

import pytest

import app.lambda_handler


def _http_api_v2_event(path: str, method: str = "GET") -> dict:
    """A minimal API Gateway HTTP API (payload v2.0) event, as CloudFront
    -> API Gateway delivers it: the full /api/... path, unstripped."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "example.cloudfront.net", "accept": "application/json"},
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "api-id",
            "domainName": "example.cloudfront.net",
            "domainPrefix": "example",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.1",
                "userAgent": "pytest",
            },
            "requestId": "request-id",
            "routeKey": "$default",
            "stage": "$default",
            "time": "29/Sep/2026:00:00:00 +0000",
            "timeEpoch": 1790640000000,
        },
        "isBase64Encoded": False,
    }


class _LambdaContext:
    function_name = "hub-test"
    aws_request_id = "request-id"


@pytest.fixture()
def handler(monkeypatch: pytest.MonkeyPatch):
    """The handler as built with API_BASE_PATH=/api, the value the Lambda
    runs with. Reloaded because the env var is read at import."""
    monkeypatch.setenv("API_BASE_PATH", "/api")
    module = importlib.reload(app.lambda_handler)
    yield module.handler
    monkeypatch.delenv("API_BASE_PATH")
    importlib.reload(app.lambda_handler)


def test_api_prefix_is_stripped_before_routing(handler):
    response = handler(_http_api_v2_event("/api/health"), _LambdaContext())

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}


def test_prefixed_protected_route_reaches_auth_not_404(handler):
    """401, not 404: the route was matched after stripping /api, and the
    auth dependency ran and rejected the missing token."""
    response = handler(_http_api_v2_event("/api/projects"), _LambdaContext())

    assert response["statusCode"] == 401
