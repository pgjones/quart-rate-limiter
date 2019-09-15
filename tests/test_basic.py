from datetime import datetime, timedelta

import pytest
from _pytest.monkeypatch import MonkeyPatch
from quart import Quart, ResponseReturnValue

import quart_rate_limiter
from quart_rate_limiter import rate_limit, RateLimiter


@pytest.fixture(name="fixed_datetime")
def _fixed_datetime(monkeypatch: MonkeyPatch) -> datetime:
    class MockDatetime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:
            return datetime(2019, 3, 4)

    monkeypatch.setattr(quart_rate_limiter, "datetime", MockDatetime)
    return MockDatetime.utcnow()


@pytest.fixture(name="app")
def _app() -> Quart:
    app = Quart(__name__)

    @app.route("/rate_limit/")
    @rate_limit(1, timedelta(seconds=2))
    @rate_limit(10, timedelta(seconds=20))
    async def index() -> ResponseReturnValue:
        return ""

    RateLimiter(app)
    return app


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_rate_limit_unique_keys(app: Quart, fixed_datetime: datetime) -> None:
    test_client = app.test_client()
    response = await test_client.get("/rate_limit/", headers={"Remote-Addr": "127.0.0.1"})
    assert response.status_code == 200
    response = await test_client.get("/rate_limit/", headers={"Remote-Addr": "127.0.0.2"})
    assert response.status_code == 200
