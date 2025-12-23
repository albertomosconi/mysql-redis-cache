"""MRCServer: Manage cache invalidation for MySQL-Redis-Cache."""

import re
from typing import Any

import redis.asyncio as redis


class MRCServer:
    """Manage cache invalidation with Redis.
    
    This class provides methods to invalidate cached queries based on
    key patterns. It uses Redis SCAN for safe iteration in production.
    
    Attributes:
        redis_config: Redis configuration dictionary
        redis_client: Redis client instance (created lazily)
    """

    def __init__(self, redis_config: dict[str, Any]):
        """Initialize server with Redis configuration.
        
        Args:
            redis_config: Redis configuration dict.
                Format: {'host': 'localhost', 'port': 6379, 'password': 'pass'}
        """
        self.redis_config = redis_config
        self.redis_client: redis.Redis | None = None

    async def __aenter__(self) -> 'MRCServer':
        """Context manager entry - returns self for use in 'async with' statements."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connections."""
        await self.close_redis_connection()

    async def _connect_redis(self) -> None:
        """Connect to Redis using redis.asyncio."""
        self.redis_client = redis.Redis(**self.redis_config)

        # Test connection
        try:
            # ping() returns bool, not awaitable in some versions
            self.redis_client.ping()
        except Exception as e:
            self.redis_client = None
            print(f"Redis Client Error: {e}")

    async def close_redis_connection(self) -> None:
        """Close Redis connection gracefully."""
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None

    async def drop_outdated_cache(
        self,
        key_names: list[str],
        key_values: list[Any]
    ) -> int:
        """Delete all cached queries matching the given key patterns.
        
        Uses Redis SCAN to iterate all keys safely, builds regex from key_names
        and key_values, and deletes matching entries.
        
        Args:
            key_names: List of parameter names to match
            key_values: List of parameter values to match
            
        Returns:
            Count of deleted cache entries
            
        Example:
            await server.drop_outdated_cache(['StoreId'], [6])
            # Deletes all cache entries containing 'StoreId=6'
            
            await server.drop_outdated_cache(['StoreId', 'UserId'], [6, 123])
            # Deletes entries containing 'StoreId=6' OR 'UserId=123'
        """
        if not self.redis_client:
            await self._connect_redis()

        if not self.redis_client:
            return 0

        # Build regex pattern from key names and values
        # Format: "StoreId=6|UserId=123"
        key_patterns = []
        for name, value in zip(key_names, key_values):
            key_patterns.append(f"{name}={value}")

        key_regex_string = '|'.join(key_patterns)
        key_regex = re.compile(key_regex_string)

        # Use SCAN to iterate all keys safely (production-safe, unlike KEYS)
        deleted_count = 0
        cursor = 0

        while True:
            # SCAN returns (cursor, keys) tuple
            cursor, keys = await self.redis_client.scan(cursor)

            for key in keys:
                # Decode bytes to string if needed
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                # Delete key if it matches the regex
                if key_regex.search(key_str):
                    await self.redis_client.delete(key)
                    deleted_count += 1

            # cursor == 0 means we've completed the full iteration
            if cursor == 0:
                break

        return deleted_count
