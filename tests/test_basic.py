from datetime import datetime, timedelta

import pytest
from quart import Blueprint, Quart, ResponseReturnValue

from quart_rate_limiter import limit_blueprint, rate_exempt, RateLimit, RateLimiter


async def test_rate_limit(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/rate_limit/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"


async def test_rate_limit_unique_keys(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/", scope_base={"client": ("127.0.0.1",)})
    assert response.status_code == 200
    response = await test_client.get("/rate_limit/", scope_base={"client": ("127.0.0.2",)})
    assert response.status_code == 200


@pytest.fixture(name="app_default_limit")
def _app_default_limit() -> Quart:
    app = Quart(__name__)

    @app.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    @app.route("/exempt")
    @rate_exempt
    async def exempt() -> ResponseReturnValue:
        return ""

    rate_limit = RateLimit(1, timedelta(seconds=2))
    RateLimiter(app, default_limits=[rate_limit])
    return app


async def test_default_rate_limits(app_default_limit: Quart, fixed_datetime: datetime) -> None:
    test_client = app_default_limit.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"


async def test_rate_exempt(app_default_limit: Quart) -> None:
    test_client = app_default_limit.test_client()
    response = await test_client.get("/exempt")
    assert "RateLimit-Limit" not in response.headers
    assert "RateLimit-Remaining" not in response.headers
    assert "RateLimit-Reset" not in response.headers

    response = await test_client.get("/exempt")
    assert response.status_code == 200


async def test_rate_limit_skip_function(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/", headers={"X-Skip": "True"})
    assert response.status_code == 200
    response = await test_client.get("/rate_limit/", headers={"X-Skip": "True"})
    assert response.status_code == 200


@pytest.fixture(name="app_blueprint_limit")
def _app_blueprint_limit() -> Quart:
    app = Quart(__name__)

    blueprint = Blueprint("blue", __name__)

    @blueprint.route("/")
    async def index() -> ResponseReturnValue:
        return ""

    app.register_blueprint(blueprint)

    RateLimiter(app)
    limit_blueprint(blueprint, 1, timedelta(seconds=2))
    return app


async def test_blueprint_rate_limits(app_blueprint_limit: Quart, fixed_datetime: datetime) -> None:
    test_client = app_blueprint_limit.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "1"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["RateLimit-Reset"] == "2"

    response = await test_client.get("/")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
