"""Redis cache service — optional caching layer with graceful fallback."""

import hashlib
import json
import logging
from datetime import datetime, time as dt_time
from functools import wraps
from typing import Any, Callable, Optional

import redis.asyncio as aioredis
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None
_redis_available: bool = True


async def _get_redis() -> Optional[aioredis.Redis]:
    """Get or create the Redis client. Returns None if unavailable."""
    global _redis, _redis_available
    if _redis is not None:
        return _redis
    if not _redis_available:
        return None
    try:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis.ping()
        logger.info(f"Redis connected: {settings.redis_url}")
        return _redis
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}), caching disabled")
        _redis_available = False
        _redis = None
        return None


async def cache_get(key: str) -> Optional[str]:
    """Get a cached value by key. Returns None on miss or error."""
    r = await _get_redis()
    if not r:
        return None
    try:
        return await r.get(key)
    except Exception:
        return None


async def cache_set(key: str, value: str, ttl: int = 3600) -> bool:
    """Set a cached value with TTL (seconds). Returns True on success."""
    r = await _get_redis()
    if not r:
        return False
    try:
        await r.set(key, value, ex=ttl)
        return True
    except Exception:
        return False


async def cache_get_json(key: str) -> Optional[dict]:
    """Get and parse a cached JSON value."""
    raw = await cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def cache_set_json(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set a cached value as JSON. Handles datetime and BaseModel."""
    return await cache_set(key, _serialize(value), ttl)


async def cache_delete(key: str):
    """Delete a cached key."""
    r = await _get_redis()
    if not r:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


def _serialize(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _json_default(obj):
    if isinstance(obj, (datetime, dt_time)):
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return str(obj)


def cache_key(*parts: str) -> str:
    """Build a deterministic cache key from parts. Long parts are hashed."""
    segments = []
    for p in parts:
        if len(p) > 80:
            p = hashlib.md5(p.encode()).hexdigest()[:16]
        segments.append(p)
    return ":".join(segments)


# ── Decorator ────────────────────────────────────────────────────

def cached(prefix: str, ttl: int = 3600):
    """Decorator to cache async function results in Redis.

    Usage:
        @cached("weather", ttl=3600)
        async def get_weather(city: str) -> dict: ...

    Cache key is built from prefix + function args. Falls through on any error.
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key_parts = [prefix] + [str(a)[:100] for a in args]
            if kwargs:
                key_parts += [f"{k}={str(v)[:100]}" for k, v in sorted(kwargs.items())]
            key = cache_key(*key_parts)

            cached_val = await cache_get_json(key)
            if cached_val is not None:
                return cached_val

            result = await func(*args, **kwargs)
            await cache_set_json(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator


# ── Rate Limiter ──────────────────────────────────────────────────

async def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> tuple[bool, int]:
    """Simple sliding-window rate limiter.

    Returns (allowed: bool, remaining: int).
    Key example: "rate:user_123:search_poi"

    Uses Redis sorted set for sliding window. On Redis unavailable, always allows.
    """
    r = await _get_redis()
    if not r:
        return True, max_requests

    now = datetime.utcnow().timestamp()
    window_start = now - window_seconds

    try:
        async with r.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
            pipe.zcard(key)                                # Count remaining
            pipe.zadd(key, {str(now): now})               # Add current
            pipe.expire(key, window_seconds + 10)         # TTL
            _, count, _, _ = await pipe.execute()

        remaining = max(0, max_requests - count - 1)
        return count < max_requests, remaining
    except Exception:
        return True, max_requests
