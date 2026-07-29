from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from flask.sansio.blueprints import Blueprint
from quart import current_app, Quart, request, Response, websocket
from quart.typing import ResponseReturnValue, RouteCallable, WebsocketCallable
from werkzeug.exceptions import TooManyRequests

from .store import MemoryStore, RateLimiterStoreABC

__all__ = [
    "RateLimitExceeded",
    "WebSocketRateLimitException",
    "RateLimit",
    "RateLimiter",
    "StatusLimit",
    "WebSocketRateLimiter",
    "rate_limit",
    "rate_exempt",
    "limit_blueprint",
    "remote_addr_key",
    "websocket_key_function",
    "MemoryStore",
    "RateLimiterStoreABC",
]

UTC = timezone.utc  # Replace with direct import when 3.9 EoL
QUART_RATE_LIMITER_LIMITS_ATTRIBUTE = "_quart_rate_limiter_limits"
QUART_RATE_LIMITER_EXEMPT_ATTRIBUTE = "_quart_rate_limiter_exempt"

#: Namespaces the pseudo endpoint a StatusLimit is keyed by, keeping it
#: from colliding with a real endpoint of the same name.
STATUS_ENDPOINT_PREFIX = "__quart_rate_limiter_status__"

KeyCallable = Callable[[], Awaitable[str]]
SkipCallable = Callable[[], Awaitable[bool]]
RejectionCallable = Callable[["RateLimitExceeded"], Awaitable[ResponseReturnValue]]


class RateLimitExceeded(TooManyRequests):
    """A 429 Rate limit exceeded error.

    Arguments:
        retry_after: Seconds left till the remaining resets to the limit.
    """

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after

    def get_headers(self, *args: Any) -> List[Tuple[str, str]]:
        headers = super().get_headers(*args)
        headers.append(("Retry-After", str(self.retry_after)))
        return headers


class WebSocketRateLimitException(Exception):
    """Exception raised when WebSocket rate limit is exceeded.

    Arguments:
        retry_after: Seconds left till the remaining resets to the limit.
    """

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"WebSocket rate limit exceeded. Retry after {retry_after} seconds.")


@dataclass
class RateLimit:
    count: int
    period: timedelta
    key_function: Optional[KeyCallable] = None
    skip_function: Optional[SkipCallable] = None

    @property
    def inverse(self) -> float:
        return self.period.total_seconds() / self.count

    @property
    def key(self) -> str:
        return f"{self.count}-{self.period.total_seconds()}"


StatusMatcher = Callable[[int], bool]


@dataclass
class StatusLimit:
    """A limit charged against the outcome of a request rather than its route.

    A route limit is spent by every request that reaches it, whatever
    comes back. That leaves two gaps. A request matching no route has no
    view function to decorate, so it is not limited at all; and a request
    that is routed but rejected, a wrong password or a forbidden
    identifier, costs the client no more than one that succeeds.

    A StatusLimit closes both. It is charged once the status code is
    known, and shares a single bucket per client across every path, so an
    agent that never repeats a URL cannot dodge it by inventing a new
    one.

    .. code-block:: python

        StatusLimit("not_found", (404, 405), [RateLimit(20, timedelta(minutes=1))])
        StatusLimit("auth", (401, 403), [RateLimit(5, timedelta(minutes=1))], deny_early=True)
        StatusLimit("server_error", range(500, 600), [RateLimit(10, timedelta(minutes=1))])

    Arguments:
        name: Identifies the bucket in the store. Two StatusLimits given
            the same name share a budget. Prefer a stable name, as
            changing it discards the budgets in flight.
        status_codes: The status codes charged against *limits*, either a
            collection of codes or a predicate taking the code.
        limits: The limits to enforce, as for a route.
        deny_early: By default a client over budget is only denied the
            requests that would themselves be charged, so exhausting the
            not-found budget never costs access to the pages that do
            exist. Set True to instead reject every request from that
            client until the budget recovers, which is what you want when
            the work being protected is expensive enough that running it
            is itself the attack, such as verifying a password.
    """

    name: str
    status_codes: Union[Iterable[int], StatusMatcher]
    limits: List[RateLimit]
    deny_early: bool = False
    _matches: StatusMatcher = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.limits:
            raise ValueError("No Rate Limit(s) set")
        if callable(self.status_codes):
            self._matches = self.status_codes
        else:
            # Materialised once, as a range or generator would otherwise
            # be consumed or rescanned on every response.
            self._matches = frozenset(self.status_codes).__contains__

    def matches(self, status_code: int) -> bool:
        return self._matches(status_code)

    @property
    def endpoint(self) -> str:
        return f"{STATUS_ENDPOINT_PREFIX}{self.name}"


T = TypeVar("T", bound=Union[RouteCallable, WebsocketCallable])


def rate_limit(
    limit: Optional[int] = None,
    period: Optional[timedelta] = None,
    key_function: Optional[KeyCallable] = None,
    skip_function: Optional[SkipCallable] = None,
    *,
    limits: Optional[List[RateLimit]] = None,
) -> Callable[[T], T]:
    """A decorator to add a rate limit marker to the route.

    This should be used to wrap a route handler (or view function) to
    apply a rate limit to requests to that route. Note that it is
    important that this decorator be wrapped by the route decorator
    and not vice, versa, as below.

    .. code-block:: python

        @app.route('/')
        @rate_limit(10, timedelta(seconds=10))
        async def index():
            ...

    Arguments:
        limit: The maximum number of requests to serve within a
            period.
        period: The duration over which the number of requests must
            not exceed the *limit*.
        key_function: A coroutine function that returns a unique key
            to identify the user agent.
        limits: Optional list of limits to use. Use instead of limit
            & period,

    .. code-block:: python

        async def example_key_function() -> str:
            return request.remote_addr

    """
    if limit is not None or period is not None:
        if limits is not None:
            raise ValueError("Please use either limit & period or limits")
        limits = [RateLimit(limit, period, key_function, skip_function)]
    if limits is None:
        raise ValueError("No Rate Limit(s) set")

    def decorator(func: T) -> T:
        rate_limits = getattr(func, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, [])
        rate_limits.extend(limits)
        setattr(func, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, rate_limits)
        return func

    return decorator


def rate_exempt(func: T) -> T:
    """A decorator to mark the route as exempt from rate limits.

    This should be used to wrap a route handler (or view function) to
    ensure no rate limits are applied to the route. Note that it is
    important that this decorator be wrapped by the route decorator
    and not vice, versa, as below.

    .. code-block:: python

        @app.route('/')
        @rate_exempt
        async def index():
            ...
    """
    setattr(func, QUART_RATE_LIMITER_EXEMPT_ATTRIBUTE, True)
    return func


U = TypeVar("U", bound=Blueprint)


def limit_blueprint(
    blueprint: U,
    limit: Optional[int] = None,
    period: Optional[timedelta] = None,
    key_function: Optional[KeyCallable] = None,
    skip_function: Optional[SkipCallable] = None,
    *,
    limits: Optional[List[RateLimit]] = None,
) -> U:
    """A function to add a rate limit marker to the blueprint.

    This should be used to apply a rate limit to all routes registered
    on the blueprint.

    .. code-block:: python

        blueprint = Blueprint("name", __name__)
        limit_blueprint(blueprint, 10, timedelta(seconds=10))

    Arguments:
        blueprint: The blueprint to limit.
        limit: The maximum number of requests to serve within a
            period.
        period: The duration over which the number of requests must
            not exceed the *limit*.
        key_function: A coroutine function that returns a unique key
            to identify the user agent.
        limits: Optional list of limits to use. Use instead of limit
            & period,

    .. code-block:: python

        async def example_key_function() -> str:
            return request.remote_addr

    """
    if limit is not None or period is not None:
        if limits is not None:
            raise ValueError("Please use either limit & period or limits")
        limits = [RateLimit(limit, period, key_function, skip_function)]
    if limits is None:
        raise ValueError("No Rate Limit(s) set")

    rate_limits = getattr(blueprint, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, [])
    rate_limits.extend(limits)
    setattr(blueprint, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, rate_limits)
    return blueprint


async def remote_addr_key() -> str:
    return request.access_route[0]


class RateLimiter:
    """A Rate limiter instance.

    This can be used to initialise Rate Limiting for a given app,
    either directly,

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

    The limiter itself can be customised using the following
    arguments,

    When a RateLimiter is initialized, it automatically sets the
    ``QUART_RATE_LIMITER_STORE`` configuration key to allow
    ``WebSocketRateLimiter`` instances to automatically use the same
    store for consistent rate limiting across HTTP and WebSocket connections.

    Arguments:
        key_function: A coroutine function that returns a unique key
            to identify the user agent.
        store: The store that contains the theoretical arrival times by
            key.
        default_limits: A sequence of instances of RateLimit, these become
            the default rate limits for all routes in addition to those set
            manually using the rate_limit decorator. They will also use the
            RateLimiter's key_function if none is supplied.
        status_limits: A sequence of instances of StatusLimit, charged
            against the status code a request produces rather than the
            route it reached. Use these to limit what a route limit
            cannot see: requests that match no route, and requests that
            are refused. Leave as None to limit on routes alone.
        rejection_handler: A coroutine function taking the
            RateLimitExceeded and returning the response to send in place
            of the one the view produced. It applies only where a status
            limit rejects a request whose status could not be known
            before dispatch, which is the one path that renders a
            response and discards it. Supply a cheap one if the app's own
            429 page is expensive to build. Defaults to None, which uses
            the app's error handler as every other 429 does.
        enabled: Set to False to disable rate limiting entirely.
    """

    def __init__(
        self,
        app: Optional[Quart] = None,
        key_function: KeyCallable = remote_addr_key,
        store: Optional[RateLimiterStoreABC] = None,
        default_limits: List[RateLimit] = None,
        enabled: bool = True,
        skip_function: SkipCallable = None,
        status_limits: Optional[List[StatusLimit]] = None,
        rejection_handler: Optional[RejectionCallable] = None,
    ) -> None:
        self.key_function = key_function
        self.skip_function = skip_function
        self.rejection_handler = rejection_handler
        self.store: RateLimiterStoreABC
        if store is None:
            self.store = MemoryStore()
        else:
            self.store = store

        self._default_rate_limits = default_limits or []
        self._status_limits = status_limits or []
        self._blueprint_rate_limits: Dict[str, List[RateLimit]] = defaultdict(list)

        if app is not None:
            self.init_app(app, enabled=enabled)

    def _get_limits_for_view_function(
        self, view_func: Callable, blueprint: Optional[Blueprint]
    ) -> List[RateLimit]:
        if getattr(view_func, QUART_RATE_LIMITER_EXEMPT_ATTRIBUTE, False):
            return []
        else:
            view_limits = getattr(view_func, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, [])
            blueprint_limits = getattr(blueprint, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, [])
            return view_limits + blueprint_limits + self._default_rate_limits

    def init_app(self, app: Quart, enabled: bool = True) -> None:
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.before_serving(self._before_serving)
        app.after_serving(self._after_serving)
        app.config.setdefault("QUART_RATE_LIMITER_ENABLED", enabled)
        # Store the rate limiter store in app config for WebSocket access
        app.config["QUART_RATE_LIMITER_STORE"] = self.store

    async def _before_serving(self) -> None:
        await self.store.before_serving()

    async def _after_serving(self) -> None:
        await self.store.after_serving()

    async def _before_request(self) -> None:
        if not current_app.config["QUART_RATE_LIMITER_ENABLED"]:
            return

        await self._raise_on_early_rejection()

        endpoint = request.endpoint
        view_func = current_app.view_functions.get(endpoint)
        blueprint = current_app.blueprints.get(request.blueprint)
        if view_func is not None:
            rate_limits = [
                limit
                for limit in self._get_limits_for_view_function(view_func, blueprint)
                if not await self._should_skip(limit)
            ]
            await self._raise_on_rejection(endpoint, rate_limits)
            await self._update_limits(endpoint, rate_limits)

    async def _active_limits(self, status_limit: StatusLimit) -> List[RateLimit]:
        return [limit for limit in status_limit.limits if not await self._should_skip(limit)]

    async def _raise_on_early_rejection(self) -> None:
        """Reject before dispatch wherever the status limits allow it.

        A status limit is charged after the fact, and rejecting after the
        fact is expensive: the view ran, and the response it produced,
        error page and all, is rendered and then thrown away. An app
        whose error handler is costly pays that twice for every request
        it refuses. Two cases avoid it.
        """
        # Routing has already failed, so the status this request will
        # carry is known without dispatching it. This is the scanner
        # walking a wordlist, and it is the bulk of the volume, so it is
        # worth spending a store read on every unrouted request to serve
        # it a single rendered response instead of two.
        predicted = getattr(request.routing_exception, "code", None)

        for status_limit in self._status_limits:
            if status_limit.deny_early or (
                predicted is not None and status_limit.matches(predicted)
            ):
                await self._raise_on_rejection(
                    status_limit.endpoint, await self._active_limits(status_limit)
                )

    async def _raise_on_rejection(self, endpoint: str, rate_limits: List[RateLimit]) -> None:
        now = datetime.now(UTC)
        for rate_limit in rate_limits:
            key = await self._create_key(endpoint, rate_limit)
            # This is the GCRA rate limiting system and tat stands for
            # the theoretical arrival time.
            stored = await self.store.get(key, now)
            if stored.tzinfo is None:
                stored = stored.astimezone(UTC)
            tat = max(stored, now)
            separation = (tat - now).total_seconds()
            max_interval = rate_limit.period.total_seconds() - rate_limit.inverse
            if separation > max_interval:
                retry_after = ((tat - timedelta(seconds=max_interval)) - now).total_seconds()
                raise RateLimitExceeded(int(ceil(retry_after)))

    async def _update_limits(self, endpoint: str, rate_limits: List[RateLimit]) -> None:
        # Update the tats for all the rate limits. This must only
        # occur if no limit rejects the request.
        now = datetime.now(UTC)
        for rate_limit in rate_limits:
            key = await self._create_key(endpoint, rate_limit)
            stored = await self.store.get(key, now)
            if stored.tzinfo is None:
                stored = stored.astimezone(UTC)
            tat = max(stored, now)
            new_tat = max(tat, now) + timedelta(seconds=rate_limit.inverse)
            await self.store.set(key, new_tat)

    async def _after_request(self, response: Response) -> Response:
        if not current_app.config["QUART_RATE_LIMITER_ENABLED"]:
            return response

        endpoint = request.endpoint
        view_func = current_app.view_functions.get(endpoint)
        blueprint = current_app.blueprints.get(request.blueprint)

        # The status is only known now, which is the whole point of these
        # limits and also why they can only reject the request they are
        # charged for by replacing its response.
        charged: Optional[StatusLimit] = None
        for status_limit in self._status_limits:
            if not status_limit.matches(response.status_code):
                continue
            active = await self._active_limits(status_limit)
            if not active:
                continue
            try:
                await self._raise_on_rejection(status_limit.endpoint, active)
            except RateLimitExceeded as error:
                return await self._make_rejection_response(error)
            await self._update_limits(status_limit.endpoint, active)
            if charged is None:
                charged = status_limit

        if view_func is not None:
            rate_limits = self._get_limits_for_view_function(view_func, blueprint)
            return await self._add_headers(response, endpoint, rate_limits)
        elif charged is not None:
            # A request that matched no route has no limits of its own to
            # report, so report the first status limit it spent instead.
            return await self._add_headers(
                response, charged.endpoint, await self._active_limits(charged)
            )
        else:
            return response

    async def _add_headers(
        self, response: Response, endpoint: str, rate_limits: List[RateLimit]
    ) -> Response:
        try:
            min_limit = min(rate_limits, key=lambda rate_limit: rate_limit.period.total_seconds())
        except ValueError:
            return response  # No rate limits

        key = await self._create_key(endpoint, min_limit)
        now = datetime.now(UTC)
        stored = await self.store.get(key, now)
        if stored.tzinfo is None:
            stored = stored.astimezone(UTC)
        tat = max(stored, now)
        separation = (tat - now).total_seconds()
        remaining = int((min_limit.period.total_seconds() - separation) / min_limit.inverse)
        response.headers["RateLimit-Limit"] = str(min_limit.count)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(int(ceil(separation)))
        return response

    async def _make_rejection_response(self, error: RateLimitExceeded) -> Response:
        """Turn a rejection decided after the view ran into a response.

        An after request function cannot raise to reach the error
        handlers, the exception would surface as a 500, so the handler is
        invoked directly and its result finalised here.

        This is the only path that discards a response it has already
        built, so it is the only one a rejection_handler replaces. Every
        other rejection raises before dispatch and renders once, which is
        what a legitimate client clicking twice should get.
        """
        if self.rejection_handler is not None:
            result: Union[ResponseReturnValue, Any] = await self.rejection_handler(error)
        else:
            result = await current_app.handle_http_exception(error)
        response = await current_app.make_response(result)
        # A custom 429 handler that builds its own response would
        # otherwise drop the header the client needs to back off.
        response.headers.setdefault("Retry-After", str(error.retry_after))
        return response

    async def _create_key(self, endpoint: str, rate_limit: RateLimit) -> str:
        key_function = rate_limit.key_function or self.key_function
        key = await key_function()
        app_name = current_app.import_name
        return f"{app_name}-{endpoint}-{rate_limit.key}-{key}"

    async def _should_skip(self, rate_limit: RateLimit) -> bool:
        skip_function = rate_limit.skip_function or self.skip_function
        if skip_function is None:
            return False
        else:
            return await skip_function()


async def websocket_key_function() -> str:
    """Default key function for WebSocket connections using remote address."""
    try:
        return websocket.remote_addr
    except ImportError:
        # Fallback if websocket context is not available
        return "default"


class WebSocketRateLimiter:
    """A WebSocket rate limiter that can be used to limit WebSocket message rates.

    Similar to fastapi-limiter's WebSocketRateLimiter, this class provides
    rate limiting for WebSocket connections using the same GCRA algorithm
    as the main RateLimiter.

    By default, it automatically uses the same store as the global RateLimiter
    if one is configured. You can override this by providing a specific store.

    .. code-block:: python

        from quart import websocket
        from quart_rate_limiter import RateLimiter, WebSocketRateLimiter
        from quart_rate_limiter.redis_store import RedisStore

        # Global configuration - WebSocket rate limiter will use this automatically
        redis_store = RedisStore("redis://localhost:6379/0")
        RateLimiter(app, store=redis_store)

        @app.websocket('/ws')
        async def websocket_endpoint():
            # Uses the Redis store automatically
            ratelimit = WebSocketRateLimiter(times=1, seconds=5)

            while True:
                try:
                    data = await websocket.receive()
                    await ratelimit(websocket, context_key=data)  # context_key is optional
                    await websocket.send("Hello, world")
                except WebSocketRateLimitException:
                    await websocket.send("Rate limited")

    Arguments:
        times: The maximum number of messages allowed.
        seconds: The time period in seconds.
        minutes: The time period in minutes (alternative to seconds).
        hours: The time period in hours (alternative to seconds/minutes).
        key_function: A coroutine function that returns a unique key
            to identify the WebSocket connection.
        store: The store that contains the theoretical arrival times by key.
            If None, will automatically use the global RateLimiter's store,
            or fall back to MemoryStore if no global store is configured.
    """

    def __init__(
        self,
        times: int,
        seconds: Optional[float] = None,
        minutes: Optional[float] = None,
        hours: Optional[float] = None,
        key_function: Optional[KeyCallable] = None,
        store: Optional[RateLimiterStoreABC] = None,
    ) -> None:
        period_seconds = 0.0
        if seconds is not None:
            period_seconds += seconds
        if minutes is not None:
            period_seconds += minutes * 60
        if hours is not None:
            period_seconds += hours * 3600

        if period_seconds <= 0:
            raise ValueError("At least one of seconds, minutes, or hours must be provided and positive")

        self.rate_limit = RateLimit(
            count=times,
            period=timedelta(seconds=period_seconds),
            key_function=key_function
        )

        if store is None:
            try:
                global_store = current_app.config.get("QUART_RATE_LIMITER_STORE")
                if global_store is not None:
                    self.store = global_store
                else:
                    self.store = MemoryStore()
            except RuntimeError:
                # No application context available
                self.store = MemoryStore()
        else:
            self.store = store

        self.key_function = key_function or websocket_key_function

    async def __call__(
        self,
        websocket_connection: Any,
        context_key: Optional[str] = None
    ) -> None:
        """Check and apply rate limiting for a WebSocket message.

        Arguments:
            websocket_connection: The WebSocket connection object (usually from quart.websocket).
            context_key: Optional context key to include in the rate limit key generation.

        Raises:
            WebSocketRateLimitException: When the rate limit is exceeded.
        """
        now = datetime.now(UTC)

        base_key = await self.key_function()
        endpoint_key = "websocket"  # Generic endpoint for websockets
        if context_key:
            endpoint_key = f"websocket-{context_key}"

        key = f"websocket-{endpoint_key}-{self.rate_limit.key}-{base_key}"

        stored = await self.store.get(key, now)
        if stored.tzinfo is None:
            stored = stored.astimezone(UTC)

        tat = max(stored, now)
        separation = (tat - now).total_seconds()
        max_interval = self.rate_limit.period.total_seconds() - self.rate_limit.inverse

        if separation > max_interval:
            retry_after = ((tat - timedelta(seconds=max_interval)) - now).total_seconds()
            raise WebSocketRateLimitException(int(ceil(retry_after)))

        new_tat = max(tat, now) + timedelta(seconds=self.rate_limit.inverse)
        await self.store.set(key, new_tat)
