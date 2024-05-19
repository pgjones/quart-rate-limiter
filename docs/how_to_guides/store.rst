Changing the store
==================

By default Quart-Rate-Limiter stores the active limits in memory. This
means that each instance of the app tracks it's own limits and hence
multiple instances together will allow a higher overall limit. To
avoid this you can centralise the store so that all instances use the
same store and hence limits.

Quart-Rate-Limiter has a builtin interface to use a redis store which
can be used as so,

.. code-block:: python

    from quart_rate_limiter.redis_store import RedisStore

    redis_store = RedisStore("address")
    RateLimiter(app, store=redis_store)

Custom store
------------

Alternatively you can use a custom storage location by implementing
the :class:`~quart_rate_limiter.store.RateLimiterStoreABC` abstract
base class and then providing an instance of it to the ``RateLimiter``
on construction as above. The
:class:`~quart_rate_limiter.redis_store.RedisStore` likely provides a
good example.
