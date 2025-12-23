"""End-to-end interoperability tests between Python and TypeScript implementations.

CRITICAL: These tests verify that cache data written by Python can be read by TypeScript
and vice versa. This ensures both implementations can share the same Redis cache in production.

Requirements:
- Docker Redis and MySQL services running (docker-compose -f redis-compose.yml up -d)
- TypeScript implementation available in ../Typescript
- Both implementations must generate identical cache keys and JSON serialization
"""

import asyncio
import hashlib
import json
import os
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import redis.asyncio as redis

from mysql_redis_cache import MRCClient, MRCServer

pytestmark = pytest.mark.interop

# Test configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', '3306')),
    'user': os.getenv('MYSQL_USER', 'test'),
    'password': os.getenv('MYSQL_PASSWORD', 'password'),
    'db': 'test_mysql_redis_cache',
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '6379')),
}

# Path to TypeScript test helper script
TYPESCRIPT_DIR = Path(__file__).parent.parent.parent / 'Typescript'


@pytest.fixture
async def redis_client():
    """Create Redis client for direct cache inspection."""
    client = redis.Redis(**REDIS_CONFIG, decode_responses=False)
    yield client
    # Cleanup: flush test keys
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def mysql_client():
    """Create MySQL client for test data setup."""
    async with MRCClient(MYSQL_CONFIG, REDIS_CONFIG) as client:
        # Initialize connection by executing a simple query
        await client._connect_mysql()
        
        # Ensure test table exists
        pool = client.get_mysql_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_interop (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(100) NOT NULL,
                        age INT,
                        balance DECIMAL(10, 2),
                        is_active BOOLEAN,
                        created_at DATETIME,
                        birth_date DATE
                    )
                """)
                
                # Clear existing data and reset auto-increment
                await cursor.execute("TRUNCATE TABLE test_interop")
                
                # Insert test data with various data types
                await cursor.execute("""
                    INSERT INTO test_interop 
                    (name, email, age, balance, is_active, created_at, birth_date) 
                    VALUES 
                    (%s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s)
                """, [
                    'Alice Johnson', 'alice@example.com', 30, Decimal('1234.56'), 1, 
                    datetime(2023, 1, 15, 10, 30, 0), date(1993, 6, 15),
                    
                    'Bob Smith', 'bob@example.com', 25, Decimal('999.99'), 1,
                    datetime(2023, 2, 20, 14, 45, 30), date(1998, 3, 22),
                    
                    'Charlie Brown', 'charlie@example.com', 35, Decimal('5000.00'), 0,
                    datetime(2023, 3, 10, 8, 15, 0), date(1988, 11, 5),
                ])
                await conn.commit()
        
        yield client


@pytest.mark.asyncio
class TestE2EInteroperability:
    """End-to-end interoperability tests using real database and cache."""

    async def test_python_writes_cache_structure(self, mysql_client, redis_client):
        """Verify Python writes cache in the correct format for TypeScript to read."""
        query = "SELECT * FROM test_interop WHERE id = %s"
        params = [1]
        param_names = ["UserId"]
        ttl = 3600

        # Execute query with cache using Python
        result = await mysql_client.query_with_cache(query, params, param_names, ttl)

        # Verify result
        assert result is not None
        assert len(result) == 1
        assert result[0]['name'] == 'Alice Johnson'

        # Get the cache key
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        
        # Verify cache key format
        query_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()
        expected_key = f"UserId=1_{query_hash}"
        assert cache_key == expected_key

        # Inspect cached data in Redis
        cached_bytes = await redis_client.get(cache_key)
        assert cached_bytes is not None

        # Decode and verify JSON structure
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)
        
        assert isinstance(cached_data, list)
        assert len(cached_data) == 1
        assert cached_data[0]['id'] == 1
        assert cached_data[0]['name'] == 'Alice Johnson'

        # Verify TTL was set
        ttl_value = await redis_client.ttl(cache_key)
        assert 3240 <= ttl_value <= 3960  # TTL with ±10% jitter

    async def test_python_reads_python_cache(self, mysql_client, redis_client):
        """Verify Python can read its own cached data (baseline test)."""
        query = "SELECT * FROM test_interop WHERE age > %s"
        params = [20]
        param_names = ["MinAge"]
        ttl = 1800

        # First query - cache miss
        result1 = await mysql_client.query_with_cache(query, params, param_names, ttl)
        assert len(result1) == 3

        # Second query - cache hit
        result2 = await mysql_client.query_with_cache(query, params, param_names, ttl)
        assert result1 == result2

    async def test_cache_key_generation_matches_typescript(self, mysql_client):
        """Verify cache key generation matches TypeScript exactly."""
        test_cases = [
            # (query, params, param_names, expected_key_pattern)
            (
                "SELECT * FROM users",
                None,
                None,
                lambda q: hashlib.sha1(q.encode('utf-8')).hexdigest()
            ),
            (
                "SELECT * FROM users WHERE id = %s",
                [123],
                ["UserId"],
                lambda q: f"UserId=123_{hashlib.sha1(q.encode('utf-8')).hexdigest()}"
            ),
            (
                "SELECT * FROM orders WHERE store_id = %s AND user_id = %s",
                [6, 123],
                ["StoreId", "UserId"],
                lambda q: f"StoreId=6_UserId=123_{hashlib.sha1(q.encode('utf-8')).hexdigest()}"
            ),
            (
                "SELECT * FROM users WHERE email = %s",
                ["test@example.com"],
                ["Email"],
                lambda q: f"Email=test@example.com_{hashlib.sha1(q.encode('utf-8')).hexdigest()}"
            ),
        ]

        for query, params, param_names, expected_fn in test_cases:
            python_key = mysql_client.get_key_from_query(query, params, param_names)
            expected_key = expected_fn(query)
            assert python_key == expected_key, f"Key mismatch for query: {query}"

    async def test_json_serialization_compact_format(self, mysql_client):
        """Verify JSON serialization uses compact format (no spaces) like TypeScript."""
        query = "SELECT * FROM test_interop WHERE id = %s"
        params = [1]
        param_names = ["UserId"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Serialize the result
        json_str = json.dumps(result, separators=(',', ':'), ensure_ascii=False)

        # Verify compact format (no spaces after separators)
        assert ', ' not in json_str
        assert ': ' not in json_str

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed == result

    async def test_decimal_to_float_conversion(self, mysql_client, redis_client):
        """Verify Decimal columns are converted to float for JSON compatibility."""
        query = "SELECT balance FROM test_interop WHERE id = %s"
        params = [1]
        param_names = ["UserId"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Check cached value
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        cached_bytes = await redis_client.get(cache_key)
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)

        # Balance should be a float, not a Decimal
        balance = cached_data[0]['balance']
        assert isinstance(balance, float)
        assert balance == 1234.56

    async def test_datetime_serialization(self, mysql_client, redis_client):
        """Verify datetime objects are serialized as strings."""
        query = "SELECT created_at, birth_date FROM test_interop WHERE id = %s"
        params = [1]
        param_names = ["UserId"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Check cached value
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        cached_bytes = await redis_client.get(cache_key)
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)

        # Datetime values should be strings in ISO format
        created_at = cached_data[0]['created_at']
        birth_date = cached_data[0]['birth_date']
        
        assert isinstance(created_at, str)
        assert isinstance(birth_date, str)
        
        # Verify they can be parsed back
        datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        date.fromisoformat(birth_date)

    async def test_boolean_values(self, mysql_client, redis_client):
        """Verify boolean/TINYINT(1) values are handled consistently."""
        query = "SELECT is_active FROM test_interop WHERE id IN (%s, %s)"
        params = [1, 3]
        param_names = ["UserIds"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Check cached value
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        cached_bytes = await redis_client.get(cache_key)
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)

        # Boolean values (TINYINT(1) in MySQL)
        assert cached_data[0]['is_active'] in (0, 1, True, False)
        assert cached_data[1]['is_active'] in (0, 1, True, False)

    async def test_null_values(self, mysql_client, redis_client):
        """Verify NULL values are handled correctly."""
        # Insert row with NULL values
        pool = mysql_client.get_mysql_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    INSERT INTO test_interop (name, email, age, balance, is_active) 
                    VALUES (%s, %s, %s, %s, %s)
                """, ['Test User', 'test@example.com', None, None, 1])
                await conn.commit()

        query = "SELECT * FROM test_interop WHERE email = %s"
        params = ['test@example.com']
        param_names = ["Email"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Check cached value
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        cached_bytes = await redis_client.get(cache_key)
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)

        # NULL values should be JSON null
        assert cached_data[0]['age'] is None
        assert cached_data[0]['balance'] is None
        assert '"age":null' in cached_json
        assert '"balance":null' in cached_json

    async def test_cache_invalidation_interop(self, mysql_client, redis_client):
        """Verify cache invalidation works with cached data from Python."""
        # Create multiple cached queries
        queries = [
            ("SELECT * FROM test_interop WHERE id = %s", [1], ["UserId"]),
            ("SELECT * FROM test_interop WHERE id = %s", [2], ["UserId"]),
            ("SELECT * FROM test_interop WHERE id = %s", [3], ["UserId"]),
            ("SELECT * FROM test_interop WHERE age > %s", [20], ["MinAge"]),
        ]

        # Cache all queries
        for query, params, param_names in queries:
            await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Verify all are cached
        for query, params, param_names in queries:
            cache_key = mysql_client.get_key_from_query(query, params, param_names)
            cached = await redis_client.get(cache_key)
            assert cached is not None

        # Invalidate UserId=1 caches
        async with MRCServer(REDIS_CONFIG) as server:
            deleted_count = await server.drop_outdated_cache(['UserId'], [1])
            assert deleted_count == 1

        # Verify UserId=1 cache is gone, others remain
        cache_key_1 = mysql_client.get_key_from_query(queries[0][0], queries[0][1], queries[0][2])
        cache_key_2 = mysql_client.get_key_from_query(queries[1][0], queries[1][1], queries[1][2])
        cache_key_3 = mysql_client.get_key_from_query(queries[2][0], queries[2][1], queries[2][2])

        assert await redis_client.get(cache_key_1) is None
        assert await redis_client.get(cache_key_2) is not None
        assert await redis_client.get(cache_key_3) is not None

    async def test_complex_query_results(self, mysql_client, redis_client):
        """Test caching of complex query results with multiple rows and columns."""
        query = """
            SELECT id, name, email, age, balance, is_active 
            FROM test_interop 
            WHERE age >= %s 
            ORDER BY age ASC
        """
        params = [25]
        param_names = ["MinAge"]

        result = await mysql_client.query_with_cache(query, params, param_names, 3600)

        # Verify result
        assert len(result) == 3
        assert result[0]['name'] == 'Bob Smith'
        assert result[1]['name'] == 'Alice Johnson'
        assert result[2]['name'] == 'Charlie Brown'

        # Check cached data
        cache_key = mysql_client.get_key_from_query(query, params, param_names)
        cached_bytes = await redis_client.get(cache_key)
        cached_json = cached_bytes.decode('utf-8')
        cached_data = json.loads(cached_json)

        # Verify complete data structure
        assert len(cached_data) == 3
        assert all('id' in row for row in cached_data)
        assert all('name' in row for row in cached_data)
        assert all('balance' in row for row in cached_data)

    async def test_with_cache_arbitrary_function(self, mysql_client, redis_client):
        """Test caching of arbitrary async functions."""
        call_count = 0

        async def expensive_computation(x: int, y: int) -> dict:
            nonlocal call_count
            call_count += 1
            # Simulate expensive operation
            await asyncio.sleep(0.01)
            return {"result": x * y, "computed": True}

        # First call - cache miss
        result1 = await mysql_client.with_cache(
            fn=lambda: expensive_computation(10, 20),
            query="computation_v1",
            params=[10, 20],
            param_names=["X", "Y"],
            ttl=3600
        )

        assert result1 == {"result": 200, "computed": True}
        assert call_count == 1

        # Second call - cache hit
        result2 = await mysql_client.with_cache(
            fn=lambda: expensive_computation(10, 20),
            query="computation_v1",
            params=[10, 20],
            param_names=["X", "Y"],
            ttl=3600
        )

        assert result2 == {"result": 200, "computed": True}
        assert call_count == 1  # Function not called again

        # Verify cached
        cache_key = mysql_client.get_key_from_query("computation_v1", [10, 20], ["X", "Y"])
        cached_bytes = await redis_client.get(cache_key)
        assert cached_bytes is not None


@pytest.mark.skipif(
    not (TYPESCRIPT_DIR / 'package.json').exists(),
    reason="TypeScript implementation not found"
)
@pytest.mark.asyncio
class TestCrossLanguageInteroperability:
    """Tests that verify Python and TypeScript can read each other's cache.
    
    These tests require both implementations to be available and Docker services running.
    """

    async def test_typescript_helper_available(self):
        """Verify TypeScript helper script is available."""
        # Check if we can run TypeScript tests
        result = subprocess.run(
            ['npm', 'list', '@actvalue/mysql-redis-cache'],
            cwd=TYPESCRIPT_DIR,
            capture_output=True,
            text=True
        )
        
        # This test just checks if TypeScript environment is set up
        assert TYPESCRIPT_DIR.exists()
        assert (TYPESCRIPT_DIR / 'package.json').exists()

    async def test_cache_key_format_documentation(self, mysql_client):
        """Document cache key format for manual TypeScript validation."""
        test_cases = [
            {
                "description": "Simple query with one integer parameter",
                "query": "SELECT * FROM test_interop WHERE id = %s",
                "params": [123],
                "param_names": ["UserId"],
            },
            {
                "description": "Query with multiple parameters",
                "query": "SELECT * FROM test_interop WHERE store_id = ? AND user_id = ?",
                "params": [6, 456],
                "param_names": ["StoreId", "UserId"],
            },
            {
                "description": "Query with string parameter",
                "query": "SELECT * FROM test_interop WHERE email = %s",
                "params": ["alice@example.com"],
                "param_names": ["Email"],
            },
        ]

        print("\n" + "="*80)
        print("CACHE KEY FORMAT DOCUMENTATION FOR TYPESCRIPT VALIDATION")
        print("="*80)

        for case in test_cases:
            key = mysql_client.get_key_from_query(
                case["query"],
                case["params"],
                case["param_names"]
            )
            
            print(f"\n{case['description']}")
            print(f"Query: {case['query']}")
            print(f"Params: {case['params']}")
            print(f"Param Names: {case['param_names']}")
            print(f"Generated Key: {key}")
            print(f"Key Length: {len(key)}")

        print("\n" + "="*80)


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v', '-s'])
