from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from flask.sansio.blueprints import Blueprint
from quart import current_app, Quart, request, Response
from quart.typing import RouteCallable, WebsocketCallable
from werkzeug.exceptions import TooManyRequests

from .store import MemoryStore, RateLimiterStoreABC

QUART_RATE_LIMITER_LIMITS_ATTRIBUTE = "_quart_rate_limiter_limits"
QUART_RATE_LIMITER_EXEMPT_ATTRIBUTE = "_quart_rate_limiter_exempt"

KeyCallable = Callable[[], Awaitable[str]]
SkipCallable = Callable[[], Awaitable[bool]]


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

    Arguments:
        key_function: A coroutine function that returns a unique key
            to identify the user agent.
        store: The store that contains the theoretical arrival times by
            key.
        default_limits: A sequence of instances of RateLimit, these become
            the default rate limits for all routes in addition to those set
            manually using the rate_limit decorator. They will also use the
            RateLimiter's key_function if none is supplied.
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
    ) -> None:
        self.key_function = key_function
        self.skip_function = skip_function
        self.store: RateLimiterStoreABC
        if store is None:
            self.store = MemoryStore()
        else:
            self.store = store

        self._default_rate_limits = default_limits or []
        self._blueprint_rate_limits: Dict[str, List[RateLimit]] = defaultdict(list)

        if app is not None:
            self.init_app(app, enabled=enabled)

    def _get_limits_for_view_function(
        self, view_func: Callable, blueprint: Optional[Blueprint]
    ) -> List[RateLimit]:
        if getattr(view_func, QUART_RATE_LIMITER_EXEMPT_ATTRIBUTE, False):
            return []
        else:
            rate_limits: List[RateLimit] = getattr(
                view_func, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, []
            )
            rate_limits.extend(getattr(blueprint, QUART_RATE_LIMITER_LIMITS_ATTRIBUTE, []))
            rate_limits.extend(self._default_rate_limits)
            return rate_limits

    def init_app(self, app: Quart, enabled: bool = True) -> None:
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.before_serving(self._before_serving)
        app.after_serving(self._after_serving)
        app.config.setdefault("QUART_RATE_LIMITER_ENABLED", enabled)

    async def _before_serving(self) -> None:
        await self.store.before_serving()

    async def _after_serving(self) -> None:
        await self.store.after_serving()

    async def _before_request(self) -> None:
        if not current_app.config["QUART_RATE_LIMITER_ENABLED"]:
            return

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

    async def _raise_on_rejection(self, endpoint: str, rate_limits: List[RateLimit]) -> None:
        now = datetime.utcnow()
        for rate_limit in rate_limits:
            key = await self._create_key(endpoint, rate_limit)
            # This is the GCRA rate limiting system and tat stands for
            # the theoretical arrival time.
            tat = max(await self.store.get(key, now), now)
            separation = (tat - now).total_seconds()
            max_interval = rate_limit.period.total_seconds() - rate_limit.inverse
            if separation > max_interval:
                retry_after = ((tat - timedelta(seconds=max_interval)) - now).total_seconds()
                raise RateLimitExceeded(int(retry_after))

    async def _update_limits(self, endpoint: str, rate_limits: List[RateLimit]) -> None:
        # Update the tats for all the rate limits. This must only
        # occur if no limit rejects the request.
        now = datetime.utcnow()
        for rate_limit in rate_limits:
            key = await self._create_key(endpoint, rate_limit)
            tat = max(await self.store.get(key, now), now)
            new_tat = max(tat, now) + timedelta(seconds=rate_limit.inverse)
            await self.store.set(key, new_tat)

    async def _after_request(self, response: Response) -> Response:
        if not current_app.config["QUART_RATE_LIMITER_ENABLED"]:
            return response

        endpoint = request.endpoint
        view_func = current_app.view_functions.get(endpoint)
        blueprint = current_app.blueprints.get(request.blueprint)
        rate_limits = self._get_limits_for_view_function(view_func, blueprint)
        try:
            min_limit = min(rate_limits, key=lambda rate_limit: rate_limit.period.total_seconds())
        except ValueError:
            pass  # No rate limits
        else:
            key = await self._create_key(endpoint, min_limit)
            now = datetime.utcnow()
            tat = max(await self.store.get(key, now), now)
            separation = (tat - now).total_seconds()
            remaining = int((min_limit.period.total_seconds() - separation) / min_limit.inverse)
            response.headers["RateLimit-Limit"] = str(min_limit.count)
            response.headers["RateLimit-Remaining"] = str(remaining)
            response.headers["RateLimit-Reset"] = str(int(separation))

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
