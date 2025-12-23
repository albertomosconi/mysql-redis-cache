# MySQL-Redis-Cache

Wrapper for MySQL queries with Redis caching, available for both TypeScript and Python.

## Features

- 🚀 Async/await support
- 💾 Automatic Redis caching with Redis
- ⏱️ Configurable TTL with jitter to prevent thundering herd
- 🔑 Smart cache key generation from query and parameters
- 🧹 Selective cache invalidation
- 📦 Connection pooling for MySQL
- 🔧 Support for arbitrary function caching
- 🔄 Cross-platform compatibility (TypeScript ↔ Python)

## How It Works

### Caching Mechanism

The library intercepts MySQL queries and manages a Redis-based cache layer:

1. **Query Execution Flow**:
   - Generate cache key from query string and parameters
   - Check Redis for cached result
   - If cache hit: return cached data
   - If cache miss: execute MySQL query, cache result, return data

2. **Cache Key Format**:
   ```
   {param_name1}={value1}_{param_name2}={value2}_{SHA1_hash}
   ```
   
   Examples:
   - No parameters: `a1b2c3d4e5f6...` (SHA1 hash only)
   - With parameters: `UserId=123_StoreId=456_a1b2c3d4e5f6...`

3. **TTL Jitter Strategy**:
   To prevent cache stampede (many entries expiring simultaneously), TTL values include ±10% random jitter:
   ```
   actual_ttl = ttl + (ttl * random(-0.1, 0.1))
   ```
   
   Example: TTL of 3600s becomes 3240-3960s

4. **Data Serialization**:
   - Uses compact JSON format (no spaces) for efficient storage
   - Handles MySQL-specific types (Decimal → float, datetime → ISO string)
   - Binary-safe storage in Redis (no decode_responses)

### Cache Invalidation

Use `MRCServer` to invalidate cache entries when data changes:

```python
# After updating data
async with MRCServer(redis_config) as server:
    deleted = await server.drop_outdated_cache(['UserId'], [123])
```

The server uses Redis SCAN (not KEYS) for production-safe iteration, with regex pattern matching to find relevant cache entries.

## Implementations

### TypeScript / Node.js
📖 [TypeScript Documentation](./Typescript/README.md)

```bash
npm install @actvalue/mysql-redis-cache
```

### Python
📖 [Python Documentation](./Python/README.md)

```bash
pip install actvalue.mysql-redis-cache
```

## Cross-Platform Interoperability

**Both implementations are fully interoperable:**
- Generate identical cache keys for the same query/params
- Use identical JSON serialization format
- Store data in Redis with the same structure
- Handle all MySQL data types consistently

This ensures:
- Python can read cache written by TypeScript
- TypeScript can read cache written by Python
- Shared cache works transparently across both platforms
- No data corruption or type mismatch issues

## Quick Start

### TypeScript

```typescript
import { MRCClient } from '@actvalue/mysql-redis-cache';

const mysqlConfig = {
  host: 'localhost',
  port: 3306,
  user: 'myuser',
  password: 'mypassword',
  database: 'mydatabase',
};

const redisConfig = {
  host: 'localhost',
  port: 6379,
};

const client = new MRCClient(mysqlConfig, redisConfig);

// Execute query with caching
const result = await client.queryWithCache(
  'SELECT * FROM users WHERE id = ?',
  [123],
  ['UserId'],
  3600 // TTL in seconds
);

await client.closeRedisConnection();
```

### Python

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
}

async with MRCClient(mysql_config, redis_config) as client:
    result = await client.query_with_cache(
        'SELECT * FROM users WHERE id = ?',
        [123],
        ['UserId'],
        3600  # TTL in seconds
    )
```

## Cache Invalidation

### TypeScript

```typescript
import { MRCServer } from '@actvalue/mysql-redis-cache';

const server = new MRCServer(redisConfig);

// Delete all cached queries with StoreId = 6
const deletedCount = await server.dropOutdatedCache(['StoreId'], [6]);
console.log(`Deleted ${deletedCount} cache entries`);

await server.closeRedisConnection();
```

### Python

```python
from mysql_redis_cache import MRCServer

async with MRCServer(redis_config) as server:
    # Delete all cached queries with StoreId = 6
    deleted_count = await server.drop_outdated_cache(['StoreId'], [6])
    print(f"Deleted {deleted_count} cache entries")
```

## Development Setup

### Prerequisites

- Docker (for Redis and MySQL services)
- Node.js 18+ (for TypeScript)
- Python 3.13+ (for Python)
- uv (for Python package management)

### Setup

```bash
# Clone repository
git clone <repo-url>
cd mysql-redis-cache

# Install TypeScript dependencies
make install-ts

# Install Python dependencies
make install-py

# Start Redis and MySQL services
docker-compose -f redis-compose.yml up -d

# Run tests
make test

# Stop services
docker-compose -f redis-compose.yml down --volumes
```

## Testing

```bash
# Test TypeScript
make test-ts

# Test Python
make test-py

# Test cross-platform interoperability
make test-interop
```

## Use Cases

### 1. High-Read Workloads

Perfect for applications with frequent read operations on relatively static data:

```python
# Cache product catalog queries
products = await client.query_with_cache(
    'SELECT * FROM products WHERE category = ?',
    ['electronics'],
    ['Category'],
    ttl=3600  # 1 hour
)
```

### 2. Expensive Computations

Cache results of complex queries or aggregations:

```python
# Cache expensive analytics query
stats = await client.query_with_cache(
    '''SELECT 
        DATE(created_at) as date,
        COUNT(*) as orders,
        SUM(total) as revenue
       FROM orders 
       WHERE user_id = ?
       GROUP BY DATE(created_at)''',
    [123],
    ['UserId'],
    ttl=1800  # 30 minutes
)
```

### 3. External API Results

Cache API responses to reduce latency and API costs:

```python
async def fetch_weather(city: str):
    # Call external weather API
    pass

weather = await client.with_cache(
    fn=lambda: fetch_weather('London'),
    query='weather_api_v1',
    params=['London'],
    param_names=['City'],
    ttl=600  # 10 minutes
)
```

### 4. Multi-Service Architecture

Share cache between TypeScript and Python services:

```
┌─────────────┐         ┌─────────────┐
│   Node.js   │         │   Python    │
│   Service   │         │   Service   │
└──────┬──────┘         └──────┬──────┘
       │                       │
       └───────┬───────────────┘
               │
         ┌─────▼─────┐
         │   Redis   │
         │   Cache   │
         └─────┬─────┘
               │
         ┌─────▼─────┐
         │   MySQL   │
         │ Database  │
         └───────────┘
```

## Performance Considerations

- **Cache Hit Ratio**: Monitor cache hit rates to ensure effective caching
- **Memory Usage**: Configure appropriate Redis memory limits and eviction policies
- **Connection Pools**: Tune MySQL pool sizes based on concurrent query load
- **TTL Values**: Balance freshness requirements with cache efficiency
- **Key Distribution**: Use meaningful param_names for better cache distribution

## Advanced Usage

### Custom Cache Key Strategies

Generate cache keys based on your specific needs:

**TypeScript:**
```typescript
// Get cache key for inspection or manual cache operations
const key = client.getKeyFromQuery(
  'SELECT * FROM users WHERE id = ?',
  [123],
  ['UserId']
);
console.log(key); // "UserId=123_a1b2c3d4e5f6..."
```

**Python:**
```python
# Get cache key for inspection or manual cache operations
key = client.get_key_from_query(
    'SELECT * FROM users WHERE id = ?',
    [123],
    ['UserId']
)
print(key)  # "UserId=123_a1b2c3d4e5f6..."
```

### Manual Cache Operations

For fine-grained control, use read/write methods directly:

**Python:**
```python
# Check if cached
cached = await client.read_from_cache(query, params, param_names)

if cached is None:
    # Execute and cache manually
    result = await client.query_to_promise(query, params)
    await client.write_to_cache(query, result, params, param_names, ttl=3600)
else:
    result = cached
```

### Batch Cache Invalidation

Invalidate multiple patterns at once:

**Python:**
```python
async with MRCServer(redis_config) as server:
    # Invalidate all cache for user 123 across all stores
    await server.drop_outdated_cache(['UserId'], [123])
    
    # Invalidate specific user-store combinations
    await server.drop_outdated_cache(
        ['UserId', 'StoreId'],
        [123, 456]
    )
```

### Error Handling Best Practices

**Python:**
```python
from mysql_redis_cache import MRCClient
import logging

logger = logging.getLogger(__name__)

async def safe_query(client, query, params, param_names):
    try:
        return await client.query_with_cache(query, params, param_names)
    except ConnectionError as e:
        logger.error(f"Database connection failed: {e}")
        # Fallback to default values or retry logic
        return []
    except Exception as e:
        logger.error(f"Query failed: {e}")
        # Handle other errors
        raise
```

### Monitoring and Debugging

Track cache performance:

**Python:**
```python
import time

async def query_with_metrics(client, query, params, param_names):
    start = time.time()
    
    # Check if cached
    key = client.get_key_from_query(query, params, param_names)
    cached = await client.read_from_cache(query, params, param_names)
    
    if cached:
        elapsed = time.time() - start
        print(f"Cache HIT: {key} ({elapsed*1000:.2f}ms)")
        return cached
    else:
        result = await client.query_with_cache(query, params, param_names)
        elapsed = time.time() - start
        print(f"Cache MISS: {key} ({elapsed*1000:.2f}ms)")
        return result
```

## License

MIT

## Troubleshooting

### Redis Connection Issues

**Problem**: Redis connection fails or times out

**Solutions**:
- Verify Redis is running: `redis-cli ping` should return `PONG`
- Check Redis configuration (host, port, password)
- Ensure network connectivity and firewall rules
- For AWS ElastiCache: verify VPC and security group settings

### MySQL Pool Exhaustion

**Problem**: "Too many connections" or pool timeout errors

**Solutions**:
- Increase pool `maxsize` in configuration
- Reduce query execution time
- Monitor and close idle connections
- Use connection pooling appropriately for your workload

### Cache Inconsistency

**Problem**: Stale data returned from cache after updates

**Solutions**:
- Implement proper cache invalidation after data modifications
- Use appropriate TTL values for data volatility
- Consider write-through caching for critical data
- Use `MRCServer.drop_outdated_cache()` after updates

### Cross-Platform Key Mismatch

**Problem**: TypeScript and Python generate different cache keys

**Solutions**:
- Ensure both implementations use identical parameter names
- Verify parameter order matches exactly
- Check query strings are identical (whitespace matters)
- Update to latest version of both libraries

### Memory Issues in AWS Lambda

**Problem**: Lambda runs out of memory or connection pool grows

**Solutions**:
- Initialize client outside handler for connection reuse
- Configure appropriate pool sizes (smaller for Lambda)
- Monitor Lambda memory usage
- Consider using Lambda layers for dependencies

### Performance Degradation

**Problem**: Queries slower than expected

**Solutions**:
- Monitor cache hit ratio
- Analyze Redis memory usage and eviction policy
- Check network latency between services
- Optimize MySQL query performance
- Review TTL values and cache effectiveness

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Development

```bash
# Clone repository
git clone https://github.com/yourusername/mysql-redis-cache.git
cd mysql-redis-cache

# Install dependencies
make install

# Run tests
make test

# Run linters
make lint-ts lint-py
```
