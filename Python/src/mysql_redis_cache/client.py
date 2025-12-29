"""MRCClient: Async MySQL query execution with Redis caching."""

import hashlib
import json
import random
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import aiomysql
import redis.asyncio as redis


class MRCClient:
    """Execute MySQL queries with Redis caching support.
    
    This class provides an async interface for MySQL queries with automatic
    Redis caching. It supports context manager usage for proper resource cleanup.
    
    Attributes:
        mysql_pool: MySQL connection pool (created lazily)
        mysql_config: MySQL configuration (dict or connection string)
        redis_config: Redis configuration dictionary
        redis_client: Redis client instance (created lazily)
    
    Example:
        Basic usage with context manager::
        
            mysql_config = {
                'host': 'localhost',
                'port': 3306,
                'user': 'myuser',
                'password': 'mypass',
                'db': 'mydb'
            }
            redis_config = {'host': 'localhost', 'port': 6379}
            
            async with MRCClient(mysql_config, redis_config) as client:
                result = await client.query_with_cache(
                    'SELECT * FROM users WHERE id = ?',
                    [123],
                    ['UserId'],
                    ttl=3600
                )
        
        Using connection string::
        
            client = MRCClient(
                'mysql://user:pass@localhost:3306/mydb',
                redis_config
            )
    """

    def __init__(
        self,
        mysql_config: dict[str, Any] | str,
        redis_config: dict[str, Any] | str | None = None
    ):
        """Initialize client with MySQL and optional Redis configuration.
        
        Args:
            mysql_config: MySQL configuration as dict or connection string.
                Dict format: {'host': 'localhost', 'port': 3306, 'user': 'user',
                             'password': 'pass', 'db': 'database'}
                String format: 'mysql://user:password@localhost:3306/database'
            redis_config: Optional Redis configuration as dict or URL string.
                Dict format: {'host': 'localhost', 'port': 6379, 'password': 'pass'}
                URL format: 'redis://localhost:6379?decode_responses=True&health_check_interval=2'
        """
        self.mysql_pool: aiomysql.Pool | None = None
        self.mysql_config = mysql_config
        self.redis_config = redis_config
        self.redis_client: redis.Redis | None = None

    async def __aenter__(self) -> 'MRCClient':
        """Context manager entry - returns self for use in 'async with' statements."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - cleanup connections."""
        await self.close_redis_connection()
        if self.mysql_pool:
            self.mysql_pool.close()
            await self.mysql_pool.wait_closed()

    def _parse_connection_string(self, conn_str: str) -> dict[str, Any]:
        """Parse MySQL connection string into configuration dict.
        
        Args:
            conn_str: Connection string like 'mysql://user:password@localhost:3306/database'
            
        Returns:
            Dictionary with parsed connection parameters
        """
        parsed = urlparse(conn_str)
        config = {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 3306,
            'user': parsed.username or '',
            'password': parsed.password or '',
            'db': parsed.path.lstrip('/') if parsed.path else '',
        }
        return config

    async def _connect_mysql(self) -> None:
        """Create MySQL connection pool using aiomysql."""
        if isinstance(self.mysql_config, str):
            config = self._parse_connection_string(self.mysql_config)
        else:
            config = self.mysql_config.copy()

        # Extract pool-specific parameters
        minsize = config.pop('minsize', 1)
        maxsize = config.pop('maxsize', 10)

        self.mysql_pool = await aiomysql.create_pool(
            minsize=minsize,
            maxsize=maxsize,
            **config
        )

    async def _connect_redis(self) -> None:
        """Connect to Redis using redis.asyncio.
        
        Supports both dictionary config and URL string format.
        """
        if not self.redis_config:
            return

        try:
            if isinstance(self.redis_config, str):
                self.redis_client = redis.from_url(self.redis_config)
            else:
                self.redis_client = redis.Redis(**self.redis_config)
        except Exception as e:
            self.redis_client = None
            print(f"Redis Client Error: {e}")

    async def close_redis_connection(self) -> None:
        """Close Redis connection gracefully."""
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None

    def get_mysql_pool(self) -> aiomysql.Pool | None:
        """Return MySQL pool for direct database access.
        
        Creates the pool if it doesn't exist yet.
        
        Returns:
            MySQL connection pool or None if not initialized
        """
        if not self.mysql_pool:
            # This is a synchronous method but pool creation is async
            # In practice, users should await other methods first
            raise RuntimeError("MySQL pool not initialized. Call an async method first.")
        return self.mysql_pool

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Normalize a database row for JSON serialization.
        
        Converts Decimal to float and datetime objects to ISO strings
        to ensure compatibility with TypeScript JSON.stringify().
        
        Args:
            row: Dictionary representing a database row
            
        Returns:
            Normalized dictionary ready for JSON serialization
        """
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                normalized[key] = float(value)
            elif isinstance(value, (datetime, date)):
                normalized[key] = value.isoformat()
            elif isinstance(value, bytes):
                normalized[key] = value.decode('utf-8', errors='ignore')
            else:
                normalized[key] = value
        return normalized

    async def query_to_promise(
        self,
        query: str,
        params: list[Any] | None = None
    ) -> Any:
        """Execute MySQL query and return results.
        
        Args:
            query: MySQL query string (use %s for parameters)
            params: Optional list of query parameters
            
        Returns:
            Query results as list of dictionaries
        """
        if not self.mysql_pool:
            await self._connect_mysql()

        if not self.mysql_pool:
            raise RuntimeError("Failed to initialize MySQL pool")

        async with self.mysql_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
                # Normalize rows for JSON serialization
                return [self._normalize_row(row) for row in rows]

    def get_key_from_query(
        self,
        query: str,
        params: list[Any] | None = None,
        param_names: list[str] = []
    ) -> str:
        """Generate cache key using SHA1(query) + param_names=param_values.
        
        Args:
            query: MySQL query string
            params: Optional list of query parameters
            param_names: Names corresponding to parameters
            
        Returns:
            Cache key string in format: "name1=value1_name2=value2_hash"
            
        Example::
        
            # Without parameters
            key = client.get_key_from_query('SELECT * FROM users')
            # Returns: "a1b2c3d4e5f6..." (just SHA1 hash)
            
            # With parameters
            key = client.get_key_from_query(
                'SELECT * FROM users WHERE id = ? AND store = ?',
                [123, 456],
                ['UserId', 'StoreId']
            )
            # Returns: "UserId=123_StoreId=456_a1b2c3d4e5f6..."
        """
        hash_hex = hashlib.sha1(query.encode('utf-8')).hexdigest()
        key = ''

        if params and len(params) > 0:
            for name, value in zip(param_names, params):
                key += f"{name}={value}_"

        key += hash_hex
        return key

    async def read_from_cache(
        self,
        query: str,
        params: list[Any] | None = None,
        param_names: list[str] = []
    ) -> Any | None:
        """Read cached query result from Redis.
        
        Args:
            query: MySQL query string
            params: Optional list of query parameters
            param_names: Names corresponding to parameters
            
        Returns:
            Cached result if found, None otherwise
        """
        if not self.redis_client:
            await self._connect_redis()

        if not self.redis_client:
            return None

        key = self.get_key_from_query(query, params, param_names)
        result = await self.redis_client.get(key)

        if result:
            return json.loads(result)
        return None

    async def write_to_cache(
        self,
        query: str,
        value: Any,
        params: list[Any] | None = None,
        param_names: list[str] = [],
        ttl: int = 86400
    ) -> None:
        """Write query result to cache with TTL jitter.
        
        Adds ±10% jitter to TTL to prevent thundering herd problem.
        
        Args:
            query: MySQL query string
            value: Value to cache
            params: Optional list of query parameters
            param_names: Names corresponding to parameters
            ttl: Time to live in seconds (default: 86400 = 24 hours)
        """
        if not self.redis_client:
            await self._connect_redis()

        if not self.redis_client:
            return

        key = self.get_key_from_query(query, params, param_names)

        # Add TTL jitter (±10%) to prevent cache stampede
        dt = round(ttl * random.uniform(-0.1, 0.1))
        ttl_with_jitter = ttl + dt

        # Serialize to JSON with compact format (no spaces) to match TypeScript
        json_value = json.dumps(value, separators=(',', ':'), ensure_ascii=False)

        await self.redis_client.set(key, json_value, ex=ttl_with_jitter)

    async def with_cache(
        self,
        fn: Callable[[], Awaitable[Any]],
        query: str,
        params: list[Any] | None = None,
        param_names: list[str] = [],
        ttl: int = 86400
    ) -> Any:
        """Execute arbitrary async function with caching.
        
        This is a critical feature that allows caching of any async function result.
        
        Args:
            fn: Async function to execute (takes no args, returns result)
            query: Query signature for cache key generation
            params: Optional list of parameters for cache key
            param_names: Names corresponding to parameters
            ttl: Time to live in seconds (default: 86400 = 24 hours)
            
        Returns:
            Function result (from cache or fresh execution)
            
        Example::
        
            # Cache expensive computation
            async def calculate_stats(user_id: int) -> dict:
                # Complex calculation
                await asyncio.sleep(5)
                return {'total': 100, 'average': 25}
            
            result = await client.with_cache(
                fn=lambda: calculate_stats(123),
                query='user_stats_v1',
                params=[123],
                param_names=['UserId'],
                ttl=3600
            )
            
            # Cache API call
            async def fetch_external_data():
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://api.example.com/data') as resp:
                        return await resp.json()
            
            data = await client.with_cache(
                fn=fetch_external_data,
                query='external_api_v1',
                ttl=600
            )
        """
        if not self.redis_client:
            await self._connect_redis()

        if not self.redis_client:
            # No Redis, just execute function
            return await fn()

        # Try to get from cache
        key = self.get_key_from_query(query, params, param_names)
        result = await self.redis_client.get(key)

        if result:
            return json.loads(result)

        # Execute function
        r = await fn()

        # Cache result with jitter
        dt = round(ttl * random.uniform(-0.1, 0.1))
        ttl_with_jitter = ttl + dt
        json_value = json.dumps(r, separators=(',', ':'), ensure_ascii=False)
        await self.redis_client.set(key, json_value, ex=ttl_with_jitter)

        return r

    async def query_with_cache(
        self,
        query: str,
        params: list[Any] | None = None,
        param_names: list[str] = [],
        ttl: int = 86400
    ) -> Any:
        """Execute MySQL query with caching.
        
        Main convenience method for cached queries.
        
        Args:
            query: MySQL query string
            params: Optional list of query parameters
            param_names: Names corresponding to parameters
            ttl: Time to live in seconds (default: 86400 = 24 hours)
            
        Returns:
            Query results (from cache or fresh execution)
            
        Example::
        
            # Simple query without parameters
            users = await client.query_with_cache(
                'SELECT * FROM users',
                ttl=3600
            )
            
            # Parameterized query
            user = await client.query_with_cache(
                'SELECT * FROM users WHERE id = ?',
                [123],
                ['UserId'],
                ttl=3600
            )
            
            # Complex query with multiple parameters
            orders = await client.query_with_cache(
                'SELECT * FROM orders WHERE user_id = ? AND status = ?',
                [123, 'completed'],
                ['UserId', 'Status'],
                ttl=1800
            )
        """
        async def fn() -> Any:
            return await self.query_to_promise(query, params)

        return await self.with_cache(fn, query, params, param_names, ttl)
