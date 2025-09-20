WebSocket Rate Limiting
=======================

Quart-Rate-Limiter provides comprehensive support for rate limiting WebSocket
connections, allowing you to control message rates per connection or per user.

Basic Usage
-----------

The simplest way to add rate limiting to a WebSocket endpoint is to use the
``WebSocketRateLimiter`` class:

.. code-block:: python

    from quart import Quart, websocket
    from quart_rate_limiter import WebSocketRateLimiter, WebSocketRateLimitException

    app = Quart(__name__)

    @app.websocket('/ws')
    async def websocket_endpoint():
        # Allow 1 message per 5 seconds
        ratelimit = WebSocketRateLimiter(times=1, seconds=5)

        await websocket.accept()
        while True:
            try:
                data = await websocket.receive()
                await ratelimit(websocket)
                await websocket.send(f"Echo: {data}")
            except WebSocketRateLimitException:
                await websocket.send("Rate limited!")

Time Periods
------------

``WebSocketRateLimiter`` supports multiple time units that can be combined:

.. code-block:: python

    # 10 messages per minute
    limiter1 = WebSocketRateLimiter(times=10, minutes=1)

    # 100 messages per hour
    limiter2 = WebSocketRateLimiter(times=100, hours=1)

    # 5 messages per 1 hour 30 minutes 30 seconds (5430 seconds total)
    limiter3 = WebSocketRateLimiter(times=5, hours=1, minutes=30, seconds=30)

Context Keys
------------

Use context keys to differentiate between different types of messages or actions:

.. code-block:: python

    @app.websocket('/ws')
    async def websocket_endpoint():
        ratelimit = WebSocketRateLimiter(times=1, seconds=5)

        await websocket.accept()
        while True:
            try:
                data = await websocket.receive_json()

                # Different limits for different message types
                if data['type'] == 'chat':
                    await ratelimit(websocket, context_key='chat')
                elif data['type'] == 'command':
                    await ratelimit(websocket, context_key='command')

                await websocket.send_json({"status": "processed"})
            except WebSocketRateLimitException as e:
                await websocket.send_json({
                    "error": "rate_limited",
                    "retry_after": e.retry_after
                })

Custom Key Functions
--------------------

Use custom key functions to implement user-specific rate limiting:

.. code-block:: python

    @app.websocket('/ws')
    async def websocket_endpoint():
        # Extract user ID from query parameters
        user_id = websocket.args.get('user_id', 'anonymous')

        async def user_key():
            return f"user:{user_id}"

        ratelimit = WebSocketRateLimiter(
            times=10,
            minutes=1,
            key_function=user_key
        )

        await websocket.accept()
        while True:
            try:
                data = await websocket.receive()
                await ratelimit(websocket)
                await websocket.send(f"User {user_id}: {data}")
            except WebSocketRateLimitException:
                await websocket.send("User rate limit exceeded!")

Storage Backends
----------------

WebSocket rate limiting supports the same storage backends as HTTP rate limiting.

Automatic Store Detection
~~~~~~~~~~~~~~~~~~~~~~~~~

By default, ``WebSocketRateLimiter`` automatically uses the same store as your
global ``RateLimiter`` configuration. This is achieved through the ``QUART_RATE_LIMITER_STORE``
configuration key, which is automatically set when you initialize a ``RateLimiter``:

.. code-block:: python

    from quart_rate_limiter import RateLimiter, WebSocketRateLimiter
    from quart_rate_limiter.redis_store import RedisStore

    # Global configuration - automatically sets QUART_RATE_LIMITER_STORE
    redis_store = RedisStore("redis://localhost:6379/0")
    RateLimiter(app, store=redis_store)

    # WebSocket rate limiter automatically detects and uses the Redis store
    @app.websocket('/ws')
    async def websocket_endpoint():
        ratelimit = WebSocketRateLimiter(times=1, seconds=5)  # Uses Redis automatically
        # ... rest of websocket logic

.. note::
   The ``QUART_RATE_LIMITER_STORE`` configuration key is managed automatically
   and should not be set manually. It ensures that WebSocket rate limiting uses
   the same storage backend as your HTTP rate limiting for consistency.

Manual Store Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

If you need different storage backends for WebSocket and HTTP rate limiting,
you can explicitly provide a store to override the automatic detection:

.. code-block:: python

    from quart_rate_limiter import RateLimiter, WebSocketRateLimiter
    from quart_rate_limiter.redis_store import RedisStore

    # Global configuration
    redis_store = RedisStore("redis://localhost:6379/0")
    RateLimiter(app, store=redis_store)

    # WebSocket rate limiter automatically uses the Redis store
    @app.websocket('/ws')
    async def websocket_endpoint():
        ratelimit = WebSocketRateLimiter(times=1, seconds=5)  # Uses Redis automatically
        # ... rest of websocket logic

Memory Store (Default fallback)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If no global store is configured, ``MemoryStore`` is used by default:

.. code-block:: python

    from quart_rate_limiter import MemoryStore

    # Explicit memory store (optional, this is the default)
    store = MemoryStore()
    ratelimit = WebSocketRateLimiter(times=1, seconds=5, store=store)

Redis Store
~~~~~~~~~~~

Use Redis for distributed rate limiting across multiple application instances:

.. code-block:: python

    from quart_rate_limiter.redis_store import RedisStore

    store = RedisStore("redis://localhost:6379/0")

    @app.websocket('/ws')
    async def websocket_endpoint():
        ratelimit = WebSocketRateLimiter(times=1, seconds=5, store=store)

        await websocket.accept()
        # ... rest of websocket logic

Valkey Store
~~~~~~~~~~~~

Valkey can be used as an alternative to Redis:

.. code-block:: python

    from quart_rate_limiter.valkey_store import ValkeyStore

    store = ValkeyStore("valkey://localhost:6379/0")
    ratelimit = WebSocketRateLimiter(times=1, seconds=5, store=store)

Error Handling
--------------

The ``WebSocketRateLimitException`` includes useful information for handling rate limits:

.. code-block:: python

    @app.websocket('/ws')
    async def websocket_endpoint():
        ratelimit = WebSocketRateLimiter(times=5, minutes=1)

        await websocket.accept()
        while True:
            try:
                data = await websocket.receive()
                await ratelimit(websocket)
                await websocket.send(f"Processing: {data}")
            except WebSocketRateLimitException as e:
                # e.retry_after contains seconds until limit resets
                await websocket.send_json({
                    "error": "Rate limit exceeded",
                    "retry_after": e.retry_after,
                    "message": str(e)
                })

Advanced Example
----------------

Here's a comprehensive example with authentication, multiple rate limits, and error handling:

.. code-block:: python

    import json
    from quart import Quart, websocket
    from quart_rate_limiter import WebSocketRateLimiter, WebSocketRateLimitException
    from quart_rate_limiter.redis_store import RedisStore

    app = Quart(__name__)
    redis_store = RedisStore("redis://localhost:6379/0")

    @app.websocket('/ws')
    async def websocket_endpoint():
        # Get user authentication from headers or query params
        user_id = websocket.headers.get('X-User-ID') or websocket.args.get('user_id')
        if not user_id:
            await websocket.close(code=1008, reason="Authentication required")
            return

        # User-specific key function
        async def user_key():
            return f"user:{user_id}"

        # Different rate limiters for different actions
        message_limiter = WebSocketRateLimiter(
            times=30, minutes=1,
            key_function=user_key,
            store=redis_store
        )

        command_limiter = WebSocketRateLimiter(
            times=5, minutes=1,
            key_function=user_key,
            store=redis_store
        )

        await websocket.accept()

        try:
            while True:
                try:
                    raw_data = await websocket.receive()
                    data = json.loads(raw_data)

                    # Apply different rate limits based on message type
                    if data.get('type') == 'command':
                        await command_limiter(websocket, context_key='command')
                        # Process command
                        result = await process_command(data['command'])
                        await websocket.send_json({"result": result})
                    else:
                        await message_limiter(websocket, context_key='message')
                        # Process regular message
                        await websocket.send_json({"echo": data})

                except WebSocketRateLimitException as e:
                    await websocket.send_json({
                        "error": "rate_limit_exceeded",
                        "retry_after": e.retry_after,
                        "limit_type": "command" if "command" in str(e) else "message"
                    })
                except json.JSONDecodeError:
                    await websocket.send_json({"error": "invalid_json"})
                except Exception as e:
                    await websocket.send_json({"error": "server_error"})

        except Exception as e:
            print(f"WebSocket error: {e}")
        finally:
            # Cleanup if needed
            pass

    async def process_command(command):
        # Your command processing logic here
        return f"Executed: {command}"

Best Practices
--------------

1. **Choose appropriate time windows**: Consider your application's usage patterns when setting rate limits.

2. **Use context keys**: Differentiate between different types of WebSocket messages to avoid conflicting limits.

3. **Implement graceful degradation**: When rate limits are exceeded, inform users and suggest alternatives.

4. **Monitor rate limit usage**: Log rate limit violations to understand usage patterns and adjust limits accordingly.

5. **Use Redis for production**: For multi-instance deployments, use Redis or Valkey for consistent rate limiting.

6. **Handle disconnections**: Be prepared for WebSocket disconnections and reconnections affecting rate limits.

7. **Consider user experience**: Very strict rate limits can hurt user experience, while too lenient limits may not provide protection.