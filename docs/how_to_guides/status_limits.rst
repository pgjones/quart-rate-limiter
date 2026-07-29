Limiting by response status
===========================

A route limit is spent by every request that reaches the route, however
that request turns out. Two kinds of abuse slip through it.

A request that matches no route never reaches a view function, so there
is nothing to decorate and nothing is charged. This is what a scanner
walking a wordlist of ``/wp-login.php``, ``/.env``, ``/admin.php``
relies on.

A request that *is* routed but refused costs the client no more than one
that succeeds. A wrong password, a forbidden identifier or a probe for
an object that was never allocated all spend the same budget as a
legitimate call, which is far too generous for the first two.

:class:`~quart_rate_limiter.StatusLimit` closes both. It is charged once
the status code is known, and shares a single bucket per client across
every path,

.. code-block:: python

    from quart_rate_limiter import RateLimit, RateLimiter, StatusLimit

    RateLimiter(
        app,
        status_limits=[
            StatusLimit("not_found", (404, 405), [RateLimit(20, timedelta(minutes=1))]),
            StatusLimit("auth", (401, 403), [RateLimit(5, timedelta(minutes=1))]),
            StatusLimit("server_error", range(500, 600), [RateLimit(10, timedelta(minutes=1))]),
        ],
    )

The bucket is per client, not per path. A budget keyed by path would be
useless against an agent that never requests the same URL twice, as it
would never repeat a key.

Once a budget is exhausted the request is answered with a 429 carrying
``Retry-After``, built by the app's own 429 error handler as any other
is. See `What a rejection costs`_ for when that handler is entered more
than once.

``status_codes`` takes a collection of codes, a ``range``, or a
predicate,

.. code-block:: python

    StatusLimit("client_error", lambda code: 400 <= code < 500, [...])

Each limit is independent: spending the 5xx budget leaves the not-found
budget untouched. Two limits given the same ``name`` share a bucket,
which is how you spread one budget over several declarations. The name
keys the store, so changing it discards the budgets in flight.

What a rejection costs
----------------------

A status limit is charged after the fact, so rejecting can mean the view
already ran and the response it produced was rendered and then thrown
away. An app whose error page is expensive to build, one that restores a
session from Redis and renders a template, would pay that twice for
every request it refuses, and the limit would then cost more than it
saves. Which of three paths a rejection takes decides the cost.

**Routing already failed.** The status a request will carry is known
before it is dispatched, so an over budget client is rejected there and
no page is built for the response that would have been discarded. This
is the unrouted request, the scanner walking a wordlist, and it is the
bulk of the volume. It costs one store read per unrouted request and
renders once. Nothing to configure.

**A route limit rejected.** Unchanged, and it also renders once. This is
the path a legitimate client takes when it clicks twice, so it keeps the
app's own translated page.

**A route ran and refused.** ``abort(404)`` on an identifier that was
never allocated, or a wrong password, cannot be predicted: the status is
only known once the view has run. Here alone the response is built and
discarded, and the app's error handler is entered twice. Pass a
``rejection_handler`` to make the second entry cheap,

.. code-block:: python

    async def cheap_429(error: RateLimitExceeded) -> ResponseReturnValue:
        return "", 429

    RateLimiter(app, status_limits=[...], rejection_handler=cheap_429)

It replaces only that one path, so a legitimate client still gets the
full page from the two paths above. The discarded first render remains,
being the price of not knowing the status in advance.

Denying before the view runs
----------------------------

By default a client over budget is only denied the requests that would
themselves be charged. Exhausting the not-found budget therefore never
costs access to the pages that do exist, so a visitor with a stale
bookmark is not locked out of the site.

For a route that refuses, that default still lets the view run once per
attempt. Where running it is itself the attack, verifying a password
being the case that matters, that is too generous whatever the response
costs. Set ``deny_early``,

.. code-block:: python

    StatusLimit(
        "auth",
        (401, 403),
        [RateLimit(5, timedelta(minutes=1))],
        deny_early=True,
    )

The check then runs before dispatch for every request, and a client over
budget is turned away without the view running at all. The trade is that
the denial is no longer confined to the requests that would be charged:
that client is refused everything until the budget recovers. It also
costs a store read on every request, which is a round trip when the
store is Redis. Unrouted requests are already rejected before dispatch,
so a not-found limit does not need this.

Excluding assets
----------------

A single page with a broken image or a stale hashed bundle name emits
several 404s that the visitor did not choose to make, and those should
not spend the same budget as a probe. Skip them with a
``skip_function``, which works here as it does on a route limit,

.. code-block:: python

    from quart import request

    async def _skip_assets() -> bool:
        return request.path.startswith(("/static/", "/assets/", "/favicon.ico"))

    RateLimiter(
        app,
        status_limits=[
            StatusLimit(
                "not_found",
                (404, 405),
                [RateLimit(20, timedelta(minutes=1), skip_function=_skip_assets)],
            ),
        ],
    )

Reported headers
----------------

The ``RateLimit-*`` headers describe the route's own limits. A request
that matched no route has none, so they describe the first status limit
it spent instead.

.. note::

   Status limits apply to HTTP requests only. WebSocket connections are
   dispatched without the before and after request functions, so an
   unroutable WebSocket path is not charged. Use
   :class:`~quart_rate_limiter.WebSocketRateLimiter` within the handler
   for those.
