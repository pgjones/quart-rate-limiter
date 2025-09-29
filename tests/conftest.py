from datetime import datetime, timedelta, timezone
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
from quart_rate_limiter.valkey_store import ValkeyStore


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--redis-host", action="store", default=None)
    parser.addoption("--valkey-host", action="store", default=None)


@pytest.fixture(name="fixed_datetime")
def _fixed_datetime(monkeypatch: MonkeyPatch) -> datetime:
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz) -> datetime:  # type: ignore
            return datetime(2019, 3, 4, tzinfo=tz)

    monkeypatch.setattr(quart_rate_limiter, "datetime", MockDatetime)
    return MockDatetime.now(timezone.utc)


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
    valkey_host = pytestconfig.getoption("valkey_host")
    if redis_host is not None:
        store = RedisStore(f"redis://{redis_host}")
    elif valkey_host is not None:
        store = ValkeyStore(f"redis://{valkey_host}")
    else:
        store = MemoryStore()

    rate_limiter = RateLimiter(app, store=store, skip_function=_skip_function)
    app.rate_limiter = rate_limiter  # Store reference for tests
    async with app.test_app():
        yield app


@pytest.fixture(name="app_with_redis", scope="function")
async def _app_with_redis() -> AsyncGenerator[Quart, None]:
    """App fixture specifically configured with Redis store for WebSocket tests."""
    app = Quart(__name__)

    # Use a mock Redis store for testing
    try:
        from unittest.mock import AsyncMock
        redis_store = RedisStore("redis://localhost:6379/0")

        # Mock the redis client before init_app to prevent real connection attempts
        redis_store._redis = AsyncMock()
        redis_store._redis.get = AsyncMock(return_value=None)
        redis_store._redis.set = AsyncMock()
        redis_store._redis.close = AsyncMock()
        redis_store._redis.aclose = AsyncMock()

        rate_limiter = RateLimiter(app, store=redis_store)
        app.rate_limiter = rate_limiter

        # Override the store's before_serving and after_serving to prevent real Redis operations
        redis_store.before_serving = AsyncMock()
        redis_store.after_serving = AsyncMock()

        async with app.test_app():
            yield app
    except ImportError:
        pytest.skip("Redis not available")


@pytest.fixture(name="app_with_memory", scope="function")
async def _app_with_memory() -> AsyncGenerator[Quart, None]:
    """App fixture specifically configured with MemoryStore for WebSocket tests."""
    app = Quart(__name__)

    memory_store = MemoryStore()
    rate_limiter = RateLimiter(app, store=memory_store)
    app.rate_limiter = rate_limiter
    async with app.test_app():
        yield app


@pytest.fixture(name="app_no_rate_limiter", scope="function")
async def _app_no_rate_limiter() -> AsyncGenerator[Quart, None]:
    """App fixture with no RateLimiter configured for testing fallback behavior."""
    app = Quart(__name__)

    async with app.test_app():
        yield app
