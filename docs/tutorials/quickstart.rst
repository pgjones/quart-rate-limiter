.. _quickstart:

Quickstart
==========

Quart-Rate-Limiter is used by associating it with an app and then decorating
routes you'd like to rate limit,

.. code-block:: python

   from quart import Quart
   from quart_rate_limiter import RateLimiter, rate_limit

   app = Quart(__name__)
   rate_limiter = RateLimiter(app)

   @app.route('/')
   @rate_limit(1, timedelta(seconds=10))
   async def handler():
        ...
