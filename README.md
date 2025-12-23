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

## License

MIT
