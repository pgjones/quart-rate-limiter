from datetime import datetime
from typing import Any, Optional

import valkey.asyncio as valkey

from .store import RateLimiterStoreABC


class ValkeyStore(RateLimiterStoreABC):
    """An Valkey backed store of rate limits.

    Arguments:
        address: The address of the valkey instance.
        kwargs: Any keyword arguments to pass to the valkey client on
            creation, see the valkey-py documentation.
    """

    def __init__(self, address: str, **kwargs: Any) -> None:
        self._valkey: Optional[valkey.Valkey] = None
        self._valkey_arguments = (address, kwargs)

    async def before_serving(self) -> None:
        self._valkey = valkey.from_url(self._valkey_arguments[0], **self._valkey_arguments[1])

    async def get(self, key: str, default: datetime) -> datetime:
        result = await self._valkey.get(key)
        if result is None:
            return default
        else:
            return datetime.fromtimestamp(float(result))

    async def set(self, key: str, tat: datetime) -> None:
        await self._valkey.set(key, tat.timestamp())

    async def after_serving(self) -> None:
        await self._valkey.aclose()
        self._valkey = None
