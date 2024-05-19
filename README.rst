Quart-Rate-Limiter
==================

|Build Status| |docs| |pypi| |python| |license|

Quart-Rate-Limiter is an extension for `Quart
<https://github.com/pgjones/quart>`_ to allow for rate limits to be
defined and enforced on a per route basis. The 429 error response
includes a `RFC7231
<https://tools.ietf.org/html/rfc7231#section-7.1.3>`_ compliant
``Retry-After`` header and the successful responses contain headers
compliant with the `RateLimit Header Fields for HTTP
<https://tools.ietf.org/html/draft-polli-ratelimit-headers-00>`_ RFC
draft.

Quickstart
----------

To add a rate limit first initialise the RateLimiting extension with
the application, and then rate limit the route,

.. code-block:: python

    app = Quart(__name__)
    rate_limiter = RateLimiter(app)

    @app.get('/')
    @rate_limit(1, timedelta(seconds=10))
    async def handler():
        ...

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

Quart-Rate-Limiter is developed on `GitHub
<https://github.com/pgjones/quart-rate-limiter>`_. You are very welcome to
open `issues <https://github.com/pgjones/quart-rate-limiter/issues>`_ or
propose `merge requests
<https://github.com/pgjones/quart-rate-limiter/merge_requests>`_.

Testing
~~~~~~~

The best way to test Quart-Rate-Limiter is with Tox,

.. code-block:: console

    $ pip install tox
    $ tox

this will check the code style and run the tests.

Help
----

The Quart-Rate-Limiter `documentation
<https://quart-rate-limiter.readthedocs.io/en/latest/>`_ is the best
places to start, after that try searching `stack overflow
<https://stackoverflow.com/questions/tagged/quart>`_ or ask for help
`on gitter <https://gitter.im/python-quart/lobby>`_. If you still
can't find an answer please `open an issue
<https://github.com/pgjones/quart-rate-limiter/issues>`_.


.. |Build Status| image:: https://github.com/pgjones/quart-rate-limiter/actions/workflows/ci.yml/badge.svg
   :target: https://github.com/pgjones/quart-rate-limiter/commits/main

.. |docs| image:: https://readthedocs.org/projects/quart-rate-limiter/badge/?version=latest&style=flat
   :target: https://quart-rate-limiter.readthedocs.io/en/latest/

.. |pypi| image:: https://img.shields.io/pypi/v/quart-rate-limiter.svg
   :target: https://pypi.python.org/pypi/Quart-Rate-Limiter/

.. |python| image:: https://img.shields.io/pypi/pyversions/quart-rate-limiter.svg
   :target: https://pypi.python.org/pypi/Quart-Rate-Limiter/

.. |license| image:: https://img.shields.io/badge/license-MIT-blue.svg
   :target: https://github.com/pgjones/quart-rate-limiter/blob/main/LICENSE
