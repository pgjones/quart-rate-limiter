Changing the key
================

A rate limit such as ``RateLimit(1, timedelta(seconds=1))`` means that
each key can only make one 1 request per seond. By default this key is
based on the IP address of the requester as per the
:func:`~quart_rate_limiter.remote_addr_key`. This can be changed to
key on whatever you'd like by providing a ``key_function`` to the
:class:`~quart_rate_limiter.RateLimiter` or more specifically to each
:class:`~quart_rate_limiter.RateLimit`.


A common example is to key on the authenticated user's ID, which is
shown below using `Quart Auth<https://github.com/pgjones/quart-auth>`_,

.. code-block:: python

     from quart_auth import current_user
     from quart_rate_limiter import RateLimiter, remote_addr_key

     async def auth_key_function() -> str:
         if await current_user.is_authenticated:
             return current_user.auth_id
         else:
             return await remote_addr_key

     RateLimiter(app, key_function=auth_key_function)
