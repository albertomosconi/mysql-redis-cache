# actvalue.mysql-redis-cache

Async wrapper for MySQL queries with Redis caching for Python 3.13+.

## Installation

```bash
pip install actvalue.mysql-redis-cache
```

Using uv:
```bash
uv add actvalue.mysql-redis-cache
```

## Quick Start

### Client Usage

```python
from mysql_redis_cache import MRCClient

mysql_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'myuser',
    'password': 'mypassword',
    'db': 'mydatabase',
}

redis_config = {
    'host': 'localhost',
    'port': 6379,
    'password': 'mypassword',
}

# Using context manager (recommended)
async with MRCClient(mysql_config, redis_config) as client:
    # Execute query with caching
    query = 'SELECT * FROM users WHERE id = ?'
    params = [123]
    param_names = ['UserId']
    ttl = 3600  # 1 hour
    
    result = await client.query_with_cache(query, params, param_names, ttl)

# Or manual connection management
client = MRCClient(mysql_config, redis_config)
result = await client.query_with_cache(query, params, param_names, ttl)
await client.close_redis_connection()
```

### Server Usage (Cache Invalidation)

```python
from mysql_redis_cache import MRCServer

redis_config = {
    'host': 'localhost',
    'port': 6379,
    'password': 'mypassword',
}

async with MRCServer(redis_config) as server:
    # Delete all cached queries with StoreId = 6
    deleted_count = await server.drop_outdated_cache(['StoreId'], [6])
    print(f"Deleted {deleted_count} cache entries")
```

### Caching Arbitrary Functions

```python
import asyncio

async def expensive_computation(x: int, y: int) -> int:
    # Some expensive operation
    await asyncio.sleep(2)
    return x * y

# Cache the function result
result = await client.with_cache(
    fn=lambda: expensive_computation(10, 20),
    query='expensive_computation_v1',  # Signature for cache key
    params=[10, 20],
    param_names=['x', 'y'],
    ttl=3600
)
```

### Direct MySQL Pool Access

```python
# Get the MySQL pool for direct access
pool = client.get_mysql_pool()

async with pool.acquire() as conn:
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT * FROM users")
        result = await cursor.fetchall()
```

### Error Handling

```python
from mysql_redis_cache import MRCClient
import asyncio

async def main():
    try:
        async with MRCClient(mysql_config, redis_config) as client:
            result = await client.query_with_cache(
                'SELECT * FROM users WHERE id = ?',
                [123],
                ['UserId']
            )
            print(result)
    except ConnectionError as e:
        print(f"Connection failed: {e}")
    except Exception as e:
        print(f"Query failed: {e}")

asyncio.run(main())
```

### Manual Connection Management

```python
# Without context manager - requires manual cleanup
client = MRCClient(mysql_config, redis_config)

try:
    result = await client.query_with_cache(query, params, param_names)
    # Process result
finally:
    # Always clean up connections
    await client.close_redis_connection()
    if client.mysql_pool:
        client.mysql_pool.close()
        await client.mysql_pool.wait_closed()
```

## Configuration

### MySQL Configuration

**Option 1: Dictionary**
```python
mysql_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'myuser',
    'password': 'mypassword',
    'db': 'mydatabase',
    'minsize': 1,    # Connection pool minimum size
    'maxsize': 10,   # Connection pool maximum size
}
```

**Option 2: Connection String**
```python
mysql_config = 'mysql://user:password@localhost:3306/database'
```

### Redis Configuration

```python
redis_config = {
    'host': 'localhost',
    'port': 6379,
    'password': 'mypassword',
    'username': 'default',
    'decode_responses': False,  # Important: keep binary for JSON storage
    'socket_connect_timeout': 30,
}
```

## Features

### TTL with Jitter

The library automatically adds ±10% jitter to TTL values to prevent cache stampede (thundering herd problem). When many cache entries with the same TTL expire simultaneously, it can cause a spike in database load. Jitter spreads out the expiration times.

```python
# Example: TTL = 3600 seconds
# Actual TTL will be between 3240-3960 seconds (3600 ± 10%)
result = await client.query_with_cache(query, params, param_names, ttl=3600)
```

### Cache Key Generation

Cache keys are automatically generated from the query and parameters:

```python
# Format: {param_name1}={value1}_{param_name2}={value2}_{SHA1_hash}

# Example 1: No parameters
key = client.get_key_from_query('SELECT * FROM users')
# Result: "a1b2c3d4e5f6..." (just the SHA1 hash)

# Example 2: With parameters
key = client.get_key_from_query(
    'SELECT * FROM users WHERE id = ? AND store_id = ?',
    [123, 456],
    ['UserId', 'StoreId']
)
# Result: "UserId=123_StoreId=456_a1b2c3d4e5f6..."
```

### Working Without Redis

If Redis is unavailable or not configured, the library falls back to direct MySQL queries:

```python
# Redis config is optional
client = MRCClient(mysql_config)  # No Redis

# Queries will execute directly against MySQL
result = await client.query_with_cache(query, params)
```

## API Reference

### MRCClient

#### Methods

- `async __init__(mysql_config, redis_config=None)` - Initialize client
- `async __aenter__()` - Context manager entry - connect to services
- `async __aexit__(exc_type, exc_val, exc_tb)` - Context manager exit - cleanup
- `async query_with_cache(query, params=None, param_names=[], ttl=86400)` - Execute MySQL query with caching
- `async with_cache(fn, query, params=None, param_names=[], ttl=86400)` - Execute arbitrary async function with caching
- `async read_from_cache(query, params=None, param_names=[])` - Read cached query result
- `async write_to_cache(query, value, params=None, param_names=[], ttl=86400)` - Write query result to cache
- `get_key_from_query(query, params=None, param_names=[])` - Generate cache key
- `async query_to_promise(query, params=None)` - Execute MySQL query without caching
- `get_mysql_pool()` - Get MySQL connection pool for direct access
- `async close_redis_connection()` - Close Redis connection

### MRCServer

#### Methods

- `async __init__(redis_config)` - Initialize server
- `async __aenter__()` - Context manager entry
- `async __aexit__(exc_type, exc_val, exc_tb)` - Context manager exit
- `async drop_outdated_cache(key_names, key_values)` - Delete cached queries matching key patterns
- `async close_redis_connection()` - Close Redis connection

## Cache Key Format

Cache keys are generated using the format:
```
{param_name1}={value1}_{param_name2}={value2}_{SHA1_hash}
```

Examples:
- No params: `{SHA1_hash}`
- With params: `UserId=123_StoreId=456_{SHA1_hash}`

## TTL Jitter

To prevent thundering herd problems, TTL values have a ±10% random jitter applied:
```python
actual_ttl = ttl + round(ttl * random.uniform(-0.1, 0.1))
```

## Cross-Platform Compatibility

This Python implementation is fully compatible with the TypeScript version:
- Cache keys generated by Python match TypeScript exactly
- JSON serialization format is identical
- Both implementations can read each other's cached data
- MySQL data types are handled consistently

### Data Type Handling

The library automatically converts MySQL data types for cross-platform compatibility:

| MySQL Type | Python Type | JSON Type | Notes |
|------------|-------------|-----------|-------|
| INT/BIGINT | int | number | Direct mapping |
| VARCHAR/TEXT | str | string | Direct mapping |
| DECIMAL/NUMERIC | Decimal | number | Auto-converted to float |
| DATETIME | datetime | string | ISO 8601 format |
| DATE | date | string | ISO 8601 format |
| NULL | None | null | Direct mapping |
| JSON | dict | object | Direct mapping |
| BOOLEAN | int | number | 0/1 values |

### Example: Cross-Platform Cache Sharing

```python
# Python writes to cache
async with MRCClient(mysql_config, redis_config) as py_client:
    await py_client.query_with_cache(
        'SELECT id, name, price FROM products WHERE category = ?',
        ['electronics'],
        ['Category']
    )

# TypeScript can read the same cache entry
// const client = new MRCClient(mysqlConfig, redisConfig);
// const result = await client.queryWithCache(
//     'SELECT id, name, price FROM products WHERE category = ?',
//     ['electronics'],
//     ['Category']
// );
```

## Development Setup

```bash
# Clone repository
git clone <repo-url>
cd mysql-redis-cache/Python

# uv automatically creates and manages virtual environment
uv sync

# Run tests (uv handles venv activation automatically)
uv run pytest

# Run tests with coverage
uv run pytest --cov=mysql_redis_cache --cov-report=html

# Lint code
uv run ruff check src tests

# Format code
uv run ruff format src tests

# The virtual environment is created at .venv/ but you don't need to activate it manually
# All uv run commands automatically use the virtual environment
```

## Best Practices

### 1. Use Context Managers

Always use async context managers to ensure proper cleanup:

```python
async with MRCClient(mysql_config, redis_config) as client:
    # Your code here
    pass
# Connections are automatically closed
```

### 2. Choose Appropriate TTL

Set TTL based on data volatility:

```python
# Frequently changing data (user sessions)
await client.query_with_cache(query, params, param_names, ttl=300)  # 5 minutes

# Moderately changing data (product catalog)
await client.query_with_cache(query, params, param_names, ttl=3600)  # 1 hour

# Rarely changing data (configuration)
await client.query_with_cache(query, params, param_names, ttl=86400)  # 24 hours
```

### 3. Use Meaningful Parameter Names

Parameter names are part of the cache key, so use descriptive names:

```python
# Good - clear parameter names
await client.query_with_cache(
    'SELECT * FROM orders WHERE user_id = ? AND status = ?',
    [123, 'pending'],
    ['UserId', 'Status']  # Clear and descriptive
)

# Avoid - generic names make debugging harder
await client.query_with_cache(
    'SELECT * FROM orders WHERE user_id = ? AND status = ?',
    [123, 'pending'],
    ['param1', 'param2']  # Not descriptive
)
```

### 4. Cache Invalidation Strategy

Invalidate cache when data changes:

```python
from mysql_redis_cache import MRCClient, MRCServer

# When updating data
async with MRCClient(mysql_config, redis_config) as client:
    await client.query_to_promise(
        'UPDATE products SET price = ? WHERE id = ?',
        [99.99, 123]
    )

# Invalidate related cache entries
async with MRCServer(redis_config) as server:
    await server.drop_outdated_cache(['ProductId'], [123])
```

### 5. Connection Pooling

Configure appropriate pool sizes for your workload:

```python
mysql_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'myuser',
    'password': 'mypassword',
    'db': 'mydatabase',
    'minsize': 1,   # Minimum connections to maintain
    'maxsize': 10,  # Maximum concurrent connections
}
```

## AWS Lambda Usage

This library is compatible with AWS Lambda:

```python
import aiomysql
from mysql_redis_cache import MRCClient

# Initialize client outside handler for connection reuse
client = None

async def lambda_handler(event, context):
    global client
    
    # Reuse client across invocations
    if client is None:
        client = MRCClient(mysql_config, redis_config)
    
    result = await client.query_with_cache(
        'SELECT * FROM users WHERE id = ?',
        [event['userId']],
        ['UserId']
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }
```

**Lambda Considerations:**
- Connection pools persist across warm invocations
- First invocation (cold start) will be slower
- Store credentials in environment variables
- Use VPC configuration for database access

## Requirements

- Python 3.13+
- aiomysql
- redis[asyncio]

## License

MIT
