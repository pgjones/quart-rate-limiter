from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Dict


class RateLimiterStoreABC(metaclass=ABCMeta):
    @abstractmethod
    async def before_serving(self) -> None:
        """A coroutine within which any setup can be done."""
        pass

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

    @abstractmethod
    async def after_serving(self) -> None:
        """A coroutine within which any cleanup can be done."""
        pass


class MemoryStore(RateLimiterStoreABC):
    """An in memory store of rate limits."""

    def __init__(self) -> None:
        self._tats: Dict[str, datetime] = {}

    async def get(self, key: str, default: datetime) -> datetime:
        return self._tats.get(key, default)

    async def set(self, key: str, tat: datetime) -> None:
        self._tats[key] = tat

    async def before_serving(self) -> None:
        pass

    async def after_serving(self) -> None:
        pass
