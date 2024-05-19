from datetime import datetime, timedelta
from typing import AsyncGenerator

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.monkeypatch import MonkeyPatch
from quart import Quart, request, ResponseReturnValue

import quart_rate_limiter
from quart_rate_limiter import rate_limit, RateLimiter
from quart_rate_limiter.redis_store import RedisStore
from quart_rate_limiter.store import MemoryStore, RateLimiterStoreABC


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--redis-host", action="store", default=None)


@pytest.fixture(name="fixed_datetime")
def _fixed_datetime(monkeypatch: MonkeyPatch) -> datetime:
    class MockDatetime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:  # type: ignore
            return datetime(2019, 3, 4)

    monkeypatch.setattr(quart_rate_limiter, "datetime", MockDatetime)
    return MockDatetime.utcnow()


async def _skip_function() -> bool:
    return request.headers.get("X-Skip") == "True"


@pytest.fixture(name="app", scope="function")
async def _app(pytestconfig: Config) -> AsyncGenerator[Quart, None]:
    app = Quart(__name__)

    @app.route("/rate_limit/")
    @rate_limit(1, timedelta(seconds=2))
    @rate_limit(10, timedelta(seconds=20))
    async def index() -> ResponseReturnValue:
        return ""

    store: RateLimiterStoreABC
    redis_host = pytestconfig.getoption("redis_host")
    if redis_host is None:
        store = MemoryStore()
    else:
        store = RedisStore(f"redis://{redis_host}")

    RateLimiter(app, store=store, skip_function=_skip_function)
    async with app.test_app():
        yield app
