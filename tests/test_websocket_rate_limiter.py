import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from quart_rate_limiter import (
    WebSocketRateLimiter,
    WebSocketRateLimitException,
    MemoryStore,
    RateLimiter,
)


class TestWebSocketRateLimiter:
    """Test WebSocket rate limiting functionality."""

    async def _test_key_function(self) -> str:
        """Test key function that doesn't depend on Quart context."""
        return "test_client"

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_basic(self):
        """Test basic WebSocket rate limiting functionality."""
        # Create a rate limiter that allows 1 message per 2 seconds
        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)

        # Mock websocket connection
        websocket = MagicMock()

        # First call should succeed
        await limiter(websocket)

        # Second call should fail immediately
        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_context_key(self):
        """Test WebSocket rate limiting with context key."""
        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)
        websocket = MagicMock()

        # Different context keys should be tracked separately
        await limiter(websocket, context_key="user1")
        await limiter(websocket, context_key="user2")

        # Same context key should fail
        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket, context_key="user1")

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_custom_key_function(self):
        """Test WebSocket rate limiting with custom key function."""
        async def custom_key():
            return "custom_client_id"

        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=custom_key)
        websocket = MagicMock()

        await limiter(websocket)

        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_minutes(self):
        """Test WebSocket rate limiting with minutes parameter."""
        limiter = WebSocketRateLimiter(times=2, minutes=1, key_function=self._test_key_function)
        websocket = MagicMock()

        # Should allow 2 calls
        await limiter(websocket)
        await limiter(websocket)

        # Third call should fail
        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_hours(self):
        """Test WebSocket rate limiting with hours parameter."""
        limiter = WebSocketRateLimiter(times=1, hours=1, key_function=self._test_key_function)
        websocket = MagicMock()

        await limiter(websocket)

        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_multiple_time_units(self):
        """Test WebSocket rate limiting with multiple time units."""
        # 1 message per 1 hour + 30 minutes + 30 seconds = 5430 seconds
        limiter = WebSocketRateLimiter(times=1, hours=1, minutes=30, seconds=30, key_function=self._test_key_function)
        websocket = MagicMock()

        await limiter(websocket)

        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    def test_websocket_rate_limiter_invalid_time_period(self):
        """Test WebSocket rate limiter with invalid time period."""
        with pytest.raises(ValueError, match="At least one of seconds, minutes, or hours must be provided and positive"):
            WebSocketRateLimiter(times=1)

        with pytest.raises(ValueError, match="At least one of seconds, minutes, or hours must be provided and positive"):
            WebSocketRateLimiter(times=1, seconds=0)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_memory_store(self):
        """Test WebSocket rate limiting with explicit MemoryStore."""
        store = MemoryStore()
        limiter = WebSocketRateLimiter(times=1, seconds=2, store=store, key_function=self._test_key_function)
        websocket = MagicMock()

        await limiter(websocket)

        with pytest.raises(WebSocketRateLimitException):
            await limiter(websocket)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_exception_retry_after(self):
        """Test that WebSocketRateLimitException includes retry_after."""
        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)
        websocket = MagicMock()

        await limiter(websocket)

        try:
            await limiter(websocket)
            assert False, "Should have raised WebSocketRateLimitException"
        except WebSocketRateLimitException as e:
            assert hasattr(e, 'retry_after')
            assert isinstance(e.retry_after, int)
            assert e.retry_after > 0


class TestWebSocketRateLimiterWithRedis:
    """Test WebSocket rate limiting with Redis store."""

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_redis_store(self):
        """Test WebSocket rate limiting with Redis store."""
        pytest.importorskip("redis")

        from quart_rate_limiter.redis_store import RedisStore

        # Mock Redis store for testing
        store = RedisStore("redis://localhost:6379/0")
        store._redis = AsyncMock()
        store._redis.get = AsyncMock(return_value=None)
        store._redis.set = AsyncMock()

        async def test_key():
            return "redis_test_client"

        limiter = WebSocketRateLimiter(times=1, seconds=2, store=store, key_function=test_key)
        websocket = MagicMock()

        await limiter(websocket)

        # Verify Redis was called
        assert store._redis.get.called
        assert store._redis.set.called


class TestWebSocketRateLimiterWithValkey:
    """Test WebSocket rate limiting with Valkey store."""

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_with_valkey_store(self):
        """Test WebSocket rate limiting with Valkey store."""
        pytest.importorskip("valkey")

        from quart_rate_limiter.valkey_store import ValkeyStore

        # Mock Valkey store for testing
        store = ValkeyStore("valkey://localhost:6379/0")
        store._valkey = AsyncMock()
        store._valkey.get = AsyncMock(return_value=None)
        store._valkey.set = AsyncMock()

        async def test_key():
            return "valkey_test_client"

        limiter = WebSocketRateLimiter(times=1, seconds=2, store=store, key_function=test_key)
        websocket = MagicMock()

        await limiter(websocket)

        # Verify Valkey was called
        assert store._valkey.get.called
        assert store._valkey.set.called


class TestWebSocketRateLimiterGlobalStore:
    """Test WebSocket rate limiting with global store detection."""

    async def _test_key_function(self) -> str:
        """Test key function that doesn't depend on Quart context."""
        return "test_client"

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_uses_global_store(self, app_with_memory):
        """Test that WebSocketRateLimiter automatically uses global store."""
        # WebSocketRateLimiter should use the app's configured store automatically
        async with app_with_memory.app_context():
            limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)

            # Verify it's using the app's configured store
            assert limiter.store is app_with_memory.rate_limiter.store
            assert isinstance(limiter.store, MemoryStore)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_fallback_to_memory_store(self, app_no_rate_limiter):
        """Test that WebSocketRateLimiter falls back to MemoryStore when no global store."""
        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)

        # Should fallback to MemoryStore since no RateLimiter is configured
        assert isinstance(limiter.store, MemoryStore)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_no_app_context_fallback(self):
        """Test that WebSocketRateLimiter falls back to MemoryStore when no app context."""
        # Test outside of app context - should fallback to MemoryStore
        limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)

        # Should fallback to MemoryStore
        assert isinstance(limiter.store, MemoryStore)

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_explicit_store_overrides_global(self, app_with_memory):
        """Test that explicit store parameter overrides global store."""
        # Create an explicit store
        explicit_store = MemoryStore()

        # Explicit store should override global store
        limiter = WebSocketRateLimiter(
            times=1,
            seconds=2,
            key_function=self._test_key_function,
            store=explicit_store
        )

        # Should use explicit store, not global store
        assert limiter.store is explicit_store
        assert limiter.store is not app_with_memory.rate_limiter.store

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_store_integration_with_rate_limiter(self, app_with_redis):
        """Test integration with RateLimiter store configuration."""
        # WebSocketRateLimiter should automatically use Redis store from app
        async with app_with_redis.app_context():
            limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)
            websocket = MagicMock()

            await limiter(websocket)

            # Verify Redis was used
            assert limiter.store is app_with_redis.rate_limiter.store
            redis_store = app_with_redis.rate_limiter.store
            assert redis_store._redis.get.called
            assert redis_store._redis.set.called

    @pytest.mark.asyncio
    async def test_websocket_rate_limiter_functional_with_global_store(self, app_with_memory):
        """Test that rate limiting works correctly with global store."""
        async with app_with_memory.app_context():
            limiter = WebSocketRateLimiter(times=1, seconds=2, key_function=self._test_key_function)
            websocket = MagicMock()

            # First call should succeed
            await limiter(websocket)

            # Second call should fail
            with pytest.raises(WebSocketRateLimitException):
                await limiter(websocket)

            # Verify it's using the app's configured store
            assert limiter.store is app_with_memory.rate_limiter.store