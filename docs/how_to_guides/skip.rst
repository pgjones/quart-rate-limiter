Skipping limits
===============

It is often useful to have higher limits for authenticated users which
requires the default lower limit to be skipped. This is possible by
supplying a ``skip_function``, as shown below using `Quart
Auth<https://github.com/pgjones/quart-auth>`_,

.. code-block:: python

    from quart_auth import current_user

    async def skip_authenticated() -> bool:
        return await current_user.is_authenticated

    RateLimiter(
        app,
        default_limits=[
            RateLimit(1, timedelta(seconds=1), skip_function=skip_authenticated),
            RateLimit(20, timedelta(seconds=1)),
        ],
    )
