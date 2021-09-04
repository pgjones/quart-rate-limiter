Quart-Rate-Limiter
==================

|Build Status| |pypi| |python| |license|

Quart-Rate-Limiter is an extension for `Quart
<https://gitlab.com/pgjones/quart>`_ to allow for rate limits to be
defined and enforced on a per route basis. The 429 error response
includes a `RFC7231
<https://tools.ietf.org/html/rfc7231#section-7.1.3>`_ compliant
``Retry-After`` header and the successful responses contain headers
compliant with the `RateLimit Header Fields for HTTP
<https://tools.ietf.org/html/draft-polli-ratelimit-headers-00>`_ RFC
draft.

Usage
-----

To add a rate limit first initialise the RateLimiting extension with
the application,

.. code-block:: python

    app = Quart(__name__)
    rate_limiter = RateLimiter(app)

or via the factory pattern,

.. code-block:: python

    rate_limiter = RateLimiter()

    def create_app():
        app = Quart(__name__)
        rate_limiter.init_app(app)
        return app

Now this is done you can apply rate limits to any route by using the
``rate_limit`` decorator,

.. code-block:: python

    @app.route('/')
    @rate_limit(1, timedelta(seconds=10))
    async def handler():
        ...

Or to apply rate limits to all routes within a blueprint by using the
``limit_blueprint`` function,

.. code-block:: python

    blueprint = Blueprint("name", __name__)
    limit_blueprint(blueprint, 1, timedelta(seconds=10))

Or to apply rate limits to all routes in an app, define the default
limits when initialising the RateLimiter,

.. code-block:: python

    rate_limiter = RateLimiter(
        default_limits=[RateLimit(1, timedelta(seconds=10))]
    )

and then to exempt a route,

.. code-block:: python

    @app.route("/exempt")
    @rate_exempt
    async def handler():
        ...


To alter the identification of remote users you can either supply a
global key function when initialising the extension, or on a per route
basis.

By default rate limiting information (TATs) will be stored in memory,
which will result in unexpected behaviour if multiple workers are
used. To solve this a redis store can be used by installing the
``redis`` extra (``pip install quart-rate-limiter[redis]``) and then
using as so,

.. code-block:: python

    from quart_rate_limiter.redis_store import RedisStore

    redis_store = RedisStore(address)
    RateLimiter(app, store=redis_store)

This store uses `aioredis <https://github.com/aio-libs/aioredis>`_,
and any extra keyword arguments passed to the ``RedisStore``
constructor will be passed to the aioredis ``create_redis`` function.

A custom store is possible, see the ``RateLimiterStoreABC`` for the
required interface.

Simple examples
~~~~~~~~~~~~~~~

To limit a route to 1 request per second and a maximum of 20 per minute,

.. code-block:: python

    @app.route('/')
    @rate_limit(1, timedelta(seconds=1))
    @rate_limit(20, timedelta(minutes=1))
    async def handler():
        ...

Alternatively the ``limits`` argument can be used for multiple limits,

.. code-block:: python

    @app.route('/')
    @rate_limit(
        limits=[
            RateLimit(1, timedelta(seconds=1)),
            RateLimit(20, timedelta(minutes=1)),
        ],
    )
    async def handler():
        ...

To identify remote users based on their authentication ID, rather than
their IP,

.. code-block:: python

    async def key_function():
        return current_user.id

    RateLimiter(app, key_function=key_function)

The ``key_function`` is a coroutine function to allow session lookups
if appropriate.

Contributing
------------

Quart-Rate-Limiter is developed on `GitLab
<https://gitlab.com/pgjones/quart-rate-limiter>`_. You are very welcome to
open `issues <https://gitlab.com/pgjones/quart-rate-limiter/issues>`_ or
propose `merge requests
<https://gitlab.com/pgjones/quart-rate-limiter/merge_requests>`_.

Testing
~~~~~~~

The best way to test Quart-Rate-Limiter is with Tox,

.. code-block:: console

    $ pip install tox
    $ tox

this will check the code style and run the tests.

Help
----

This README is the best place to start, after that try opening an
`issue <https://gitlab.com/pgjones/quart-rate-limiter/issues>`_.


.. |Build Status| image:: https://gitlab.com/pgjones/quart-rate-limiter/badges/main/pipeline.svg
   :target: https://gitlab.com/pgjones/quart-rate-limiter/commits/main

.. |pypi| image:: https://img.shields.io/pypi/v/quart-rate-limiter.svg
   :target: https://pypi.python.org/pypi/Quart-Rate-Limiter/

.. |python| image:: https://img.shields.io/pypi/pyversions/quart-rate-limiter.svg
   :target: https://pypi.python.org/pypi/Quart-Rate-Limiter/

.. |license| image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://gitlab.com/pgjones/quart-rate-limiter/blob/main/LICENSE
