"""Unit tests for in-memory cache."""

from __future__ import annotations

import time

from hestia.web.cache import InMemoryCache


def test_cache_get_missing() -> None:
    cache = InMemoryCache()
    assert cache.get("key", 60) is None


def test_cache_set_and_get() -> None:
    cache = InMemoryCache()
    cache.set("key", {"value": 42})
    assert cache.get("key", 60) == {"value": 42}


def test_cache_expires() -> None:
    cache = InMemoryCache()
    cache.set("key", {"value": 42})
    time.sleep(0.05)
    assert cache.get("key", 0) is None


def test_cache_separate_keys() -> None:
    cache = InMemoryCache()
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a", 60) == 1
    assert cache.get("b", 60) == 2
