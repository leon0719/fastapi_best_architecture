"""
Redis connection management and utility functions.

This module provides:
- Redis connection pool management
- Automatic retry with backoff
- Cache decorator for functions
- Helper methods for common Redis operations
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

import backoff
import redis
from loguru import logger
from redis.exceptions import ConnectionError, TimeoutError

from app.common.core.config import config

# Global Redis connection pool
_redis_pool: redis.ConnectionPool | None = None
_redis_client: redis.Redis | None = None


def get_redis_pool() -> redis.ConnectionPool:
    """
    Get or create Redis connection pool.

    Returns:
        Redis connection pool instance
    """
    global _redis_pool
    if _redis_pool is None:
        logger.info(
            f"[Redis] Creating connection pool - "
            f"host: {config.redis_host}, port: {config.redis_port}, db: {config.redis_db}"
        )
        _redis_pool = redis.ConnectionPool(
            host=config.redis_host,
            port=config.redis_port,
            password=config.redis_password,
            db=config.redis_db,
            decode_responses=config.redis_decode_responses,
            max_connections=50,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
    return _redis_pool


def get_redis() -> redis.Redis:
    """
    Get Redis client with connection pool.

    Returns:
        Redis client instance

    Example:
        >>> redis_client = get_redis()
        >>> redis_client.set("key", "value", ex=60)
        >>> value = redis_client.get("key")
    """
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = redis.Redis(connection_pool=pool)
        logger.info("[Redis] Client initialized")
    return _redis_client


def close_redis():
    """
    Close Redis connections and cleanup pool.

    Call this during application shutdown.
    """
    global _redis_pool, _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
        logger.info("[Redis] Client closed")
    if _redis_pool:
        _redis_pool.disconnect()
        _redis_pool = None
        logger.info("[Redis] Connection pool closed")


@backoff.on_exception(
    backoff.expo,
    (ConnectionError, TimeoutError),
    max_tries=3,
    max_time=10,
)
def ping_redis() -> bool:
    """
    Check Redis connection health with automatic retry.

    Returns:
        True if connected, False otherwise

    Raises:
        ConnectionError: If connection fails after retries
    """
    try:
        redis_client = get_redis()
        return bool(redis_client.ping())
    except Exception as e:
        logger.exception(f"[Redis] Health check failed - error: {e}")
        return False


class RedisCache:
    """
    Redis cache utility class with helper methods.

    Example:
        >>> cache = RedisCache()
        >>> cache.set("user:123", {"name": "John"}, expire=3600)
        >>> user = cache.get("user:123")
        >>> cache.delete("user:123")
    """

    def __init__(self):
        self.client = get_redis()

    def get(self, key: str) -> str | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self.client.get(key)
            logger.debug(f"[Redis] GET - key: {key}, found: {value is not None}")
            return cast(str | None, value)
        except Exception as e:
            logger.exception(f"[Redis] GET failed - key: {key}, error: {e}")
            return None

    def get_json(self, key: str) -> Any | None:
        """
        Get JSON value from cache and deserialize.

        Args:
            key: Cache key

        Returns:
            Deserialized JSON object or None
        """
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.exception(f"[Redis] JSON decode failed - key: {key}, error: {e}")
        return None

    def set(self, key: str, value: str, expire: int | None = None) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            expire: Expiration time in seconds (optional)

        Returns:
            True if successful
        """
        try:
            # redis-py 的 set() 型別是 ResponseT(帶 get=True 時會回傳舊值的 bytes),
            # 直接內插會印出 b'...'。這裡只關心成功與否,先轉成 bool 再記錄。
            success = bool(self.client.set(key, value, ex=expire))
            logger.debug(f"[Redis] SET - key: {key}, expire: {expire}s, success: {success}")
            return success
        except Exception as e:
            logger.exception(f"[Redis] SET failed - key: {key}, expire: {expire}, error: {e}")
            return False

    def set_json(self, key: str, value: Any, expire: int | None = None) -> bool:
        """
        Serialize object to JSON and cache it.

        Args:
            key: Cache key
            value: Object to serialize and cache
            expire: Expiration time in seconds (optional)

        Returns:
            True if successful
        """
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, expire)
        except (TypeError, ValueError) as e:
            logger.exception(f"[Redis] JSON encode failed - key: {key}, error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        try:
            result = cast(int, self.client.delete(key)) > 0
            logger.debug(f"[Redis] DELETE - key: {key}, deleted: {result}")
            return result
        except Exception as e:
            logger.exception(f"[Redis] DELETE failed - key: {key}, error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        try:
            return cast(int, self.client.exists(key)) > 0
        except Exception as e:
            logger.exception(f"[Redis] EXISTS failed - key: {key}, error: {e}")
            return False

    def incr(self, key: str, amount: int = 1) -> int | None:
        """
        Increment counter.

        Args:
            key: Cache key
            amount: Increment amount (default: 1)

        Returns:
            New value after increment
        """
        try:
            result = self.client.incrby(key, amount)
            logger.debug(f"[Redis] INCR - key: {key}, amount: {amount}, new_value: {result}")
            return cast(int, result)
        except Exception as e:
            logger.exception(f"[Redis] INCR failed - key: {key}, error: {e}")
            return None

    def expire(self, key: str, seconds: int) -> bool:
        """
        Set expiration time for key.

        Args:
            key: Cache key
            seconds: Expiration time in seconds

        Returns:
            True if successful
        """
        try:
            result = self.client.expire(key, seconds)
            logger.debug(f"[Redis] EXPIRE - key: {key}, seconds: {seconds}, success: {result}")
            return bool(result)
        except Exception as e:
            logger.exception(f"[Redis] EXPIRE failed - key: {key}, error: {e}")
            return False


def cache_result(expire: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function results in Redis.

    Args:
        expire: Cache expiration time in seconds (default: 300)
        key_prefix: Prefix for cache keys (default: "")

    Returns:
        Decorator function

    Example:
        >>> @cache_result(expire=3600, key_prefix="user")
        >>> def get_user(user_id: int):
        >>>     return {"id": user_id, "name": "John"}
        >>>
        >>> # First call: fetch from DB and cache
        >>> user = get_user(123)  # Cache key: "user:get_user:123"
        >>>
        >>> # Second call: return from cache
        >>> user = get_user(123)  # Returned from cache
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key_parts = [key_prefix, func.__name__]
            if args:
                cache_key_parts.extend([str(arg) for arg in args])
            if kwargs:
                cache_key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])

            cache_key = ":".join(filter(None, cache_key_parts))

            # Try to get from cache
            cache = RedisCache()
            cached_value = cache.get_json(cache_key)
            if cached_value is not None:
                logger.info(f"[Redis] Cache HIT - key: {cache_key}")
                return cached_value

            # Cache miss - execute function
            logger.info(f"[Redis] Cache MISS - key: {cache_key}")
            result = func(*args, **kwargs)

            # Store in cache
            cache.set_json(cache_key, result, expire=expire)

            return result

        return wrapper

    return decorator
