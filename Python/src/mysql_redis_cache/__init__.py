"""MySQL-Redis-Cache: Async wrapper for MySQL queries with Redis caching.

This package provides a simple and efficient way to cache MySQL query results
using Redis, with full async/await support for Python 3.13+.

Features:
    - Automatic caching of MySQL query results
    - Configurable TTL with jitter to prevent cache stampede
    - Smart cache key generation from queries and parameters
    - Cache invalidation by key patterns
    - Cross-platform compatibility with TypeScript implementation
    - Support for arbitrary function caching

Basic Usage:
    >>> import asyncio
    >>> from mysql_redis_cache import MRCClient
    >>> 
    >>> mysql_config = {
    ...     'host': 'localhost',
    ...     'port': 3306,
    ...     'user': 'myuser',
    ...     'password': 'mypass',
    ...     'db': 'mydb'
    ... }
    >>> redis_config = {'host': 'localhost', 'port': 6379}
    >>> 
    >>> async def main():
    ...     async with MRCClient(mysql_config, redis_config) as client:
    ...         result = await client.query_with_cache(
    ...             'SELECT * FROM users WHERE id = ?',
    ...             [123],
    ...             ['UserId'],
    ...             ttl=3600
    ...         )
    ...         print(result)
    >>> 
    >>> asyncio.run(main())

See the documentation for more examples and API details.
"""

from mysql_redis_cache.client import MRCClient
from mysql_redis_cache.server import MRCServer

__all__ = ["MRCClient", "MRCServer"]
__version__ = "0.2.0"
