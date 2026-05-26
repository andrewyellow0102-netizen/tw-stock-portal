"""
In-memory cache for Yahoo Finance data.
Avoids hammering the API with repeated requests.
"""

from __future__ import annotations

import time
from typing import Any, Optional
from cachetools import TTLCache


# 60-second TTL for quotes, 30-minute TTL for OHLC
_quote_cache: TTLCache[str, Any] = TTLCache(maxsize=10_000, ttl=60)
_ohlc_cache:  TTLCache[str, Any] = TTLCache(maxsize=10_000, ttl=1800)


def get_quote_cached(key: str) -> Optional[Any]:
    return _quote_cache.get(key)


def set_quote_cached(key: str, value: Any) -> None:
    _quote_cache[key] = value


def get_ohlc_cached(key: str) -> Optional[Any]:
    return _ohlc_cache.get(key)


def set_ohlc_cached(key: str, value: Any) -> None:
    _ohlc_cache[key] = value


def clear_all_caches() -> None:
    _quote_cache.clear()
    _ohlc_cache.clear()