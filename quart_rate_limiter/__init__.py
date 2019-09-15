from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional, Type

from quart import current_app, Quart, request, Response
from quart.exceptions import HTTPException

QUART_RATE_LIMITER_ATTRIBUTE = "_quart_rate_limiter_limits"

KeyCallable = Callable[[], Awaitable[str]]


class RateLimitExceeded(HTTPException):
    """A 429 Rate limit exceeded error.

    Arguments:
        retry_after: Seconds left till the remaining resets to the limit.
    """

    def __init__(self, retry_after: int) -> None:
        super().__init__(429, "Rate Limit Exceeded", "RATE_LIMIT_EXCEEDED")
        self.retry_after = retry_after

    def get_headers(self) -> dict:
        return {"Retry-After": str(self.retry_after)}


class RateLimiterStoreABC(metaclass=ABCMeta):
    @abstractmethod
    async def get(self, key: str, default: datetime) -> datetime:
        """Get the TAT for the given *key* if present or the *default* if not.

        Arguments:
            key: The key to indentify the TAT.
            default: If no TAT for the *key* is available, return this
                default.

        Returns:
            A Theoretical Arrival Time, TAT.
        """
        pass

    @abstractmethod
    async def set(self, key: str, tat: datetime) -> None:
        """Set the TAT for the given *key*.

        Arguments:
            key: The key to indentify the TAT.
            tat: The TAT value to set.
        """
        pass


class MemoryStore(RateLimiterStoreABC):
    """An in memory store of rate limits."""

    def __init__(self) -> None:
        self._tats: Dict[str, datetime] = {}

    async def get(self, key: str, default: datetime) -> datetime:
        return self._tats.get(key, default)

    async def set(self, key: str, tat: datetime) -> None:
        self._tats[key] = tat


@dataclass
class RateLimit:
    count: int
    period: timedelta
    key_function: Optional[KeyCallable]

    @property
    def inverse(self) -> float:
        return self.period.total_seconds() / self.count

    @property
    def key(self) -> str:
        return f"{self.count}-{self.period.total_seconds()}"


def rate_limit(
    limit: int, period: timedelta, key_function: Optional[KeyCallable] = None
) -> Callable:
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

    .. code-block:: python

        async def example_key_function() -> str:
            return request.remote_addr

    """

    def decorator(func: Callable) -> Callable:
        rate_limits = getattr(func, QUART_RATE_LIMITER_ATTRIBUTE, [])
        rate_limits.append(RateLimit(limit, period, key_function))
        setattr(func, QUART_RATE_LIMITER_ATTRIBUTE, rate_limits)
        return func

    return decorator


async def remote_addr_key() -> str:
    return request.remote_addr


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
        rate_limit_exception: A type of exception to raise if the rate
            limit has been exceeded.
        store: The store that contains the theoretical arrival times by
            key.
    """

    def __init__(
        self,
        app: Optional[Quart] = None,
        key_function: KeyCallable = remote_addr_key,
        rate_limit_exception: Type[Exception] = RateLimitExceeded,
        store: Optional[RateLimiterStoreABC] = None,
    ) -> None:
        self.key_function = key_function
        self.rate_limit_exception = rate_limit_exception
        self.store: RateLimiterStoreABC
        if store is None:
            self.store = MemoryStore()
        else:
            self.store = store

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Quart) -> None:
        app.before_request(self._before_request)
        app.after_request(self._after_request)

    async def _before_request(self) -> None:
        endpoint = request.endpoint
        view_func = current_app.view_functions.get(endpoint)
        if view_func is not None:
            rate_limits: List[RateLimit] = getattr(view_func, QUART_RATE_LIMITER_ATTRIBUTE, [])
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
                raise self.rate_limit_exception(int(retry_after))

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
        endpoint = request.endpoint
        view_func = current_app.view_functions.get(endpoint)
        rate_limits: List[RateLimit] = getattr(view_func, QUART_RATE_LIMITER_ATTRIBUTE, [])
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
            max_interval = min_limit.period.total_seconds() - min_limit.inverse
            reset = int(((tat - timedelta(seconds=max_interval)) - now).total_seconds())
            response.headers["RateLimit-Limit"] = str(min_limit.count)
            response.headers["RateLimit-Remaining"] = str(remaining)
            response.headers["RateLimit-Reset"] = str(reset)
        return response

    async def _create_key(self, endpoint: str, rate_limit: RateLimit) -> str:
        key_function = rate_limit.key_function or self.key_function
        key = await key_function()
        app_name = current_app.import_name
        return f"{app_name}-{endpoint}-{rate_limit.key}-{key}"
