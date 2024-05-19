Exempting routes
================

You may decide some of your routes should be exempt from rate
limits. To do so use the :func:`~quart_rate_limiter.rate_exempt`
decorator,

.. code-block:: python

    from quart_rate_limiter import rate_exempt

    @app.get("/exempt")
    @rate_exempt
    async def handler():
        ...
