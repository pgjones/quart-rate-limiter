App wide limits
===============

It is often useful to define limits that should apply to every route
in your app by default. This removes the need to decorate every route
individually. To do so use the ``default_limits`` argument,

.. code-block:: python

    RateLimiter(
        app,
        default_limits=[
            RateLimit(1, timedelta(seconds=1)),
            RateLimit(20, timedelta(minutes=1)),
        ],
    )

Blueprint wide limits
---------------------

Alternatively you may want to set limits for all routes in a blueprint
using :func:`~quart_rate_limiter.limit_blueprint`,

.. code-block:: python

    from quart_rate_limiter import limit_blueprint

    blueprint = Blueprint("name", __name__)
    limit_blueprint(blueprint, 10, timedelta(seconds=10))

.. warning::

   These limits apply to the blueprint only and not any nested
   blueprints.
