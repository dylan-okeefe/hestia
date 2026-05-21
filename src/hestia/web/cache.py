"""In-memory cache for web route results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class CachedItem(Generic[T]):
    data: T
    cached_at: datetime


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, CachedItem[Any]] = {}

    def get(self, key: str, max_age_seconds: int) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        if datetime.now(timezone.utc) - item.cached_at > timedelta(seconds=max_age_seconds):
            return None
        return item.data

    def set(self, key: str, data: Any) -> None:
        self._store[key] = CachedItem(data=data, cached_at=datetime.now(timezone.utc))
