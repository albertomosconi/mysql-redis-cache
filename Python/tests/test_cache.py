"""Tests for MRCClient and MRCServer cache functionality."""

import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from mysql_redis_cache import MRCClient, MRCServer

pytestmark = pytest.mark.unit


class TestCacheKeyGeneration:
    """Test cache key generation logic."""

    def test_key_without_params(self):
        """Test cache key generation without parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users"

        key = client.get_key_from_query(query)

        # Should be just the SHA1 hash
        assert len(key) == 40  # SHA1 hex is 40 characters
        assert key.isalnum()  # Only hex characters

    def test_key_with_params(self):
        """Test cache key generation with parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]

        key = client.get_key_from_query(query, params, param_names)

        # Should start with param=value_
        assert key.startswith("UserId=123_")
        # Should end with 40-character hash
        assert len(key) == len("UserId=123_") + 40

    def test_key_with_multiple_params(self):
        """Test cache key generation with multiple parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM orders WHERE store_id = ? AND user_id = ?"
        params = [6, 123]
        param_names = ["StoreId", "UserId"]

        key = client.get_key_from_query(query, params, param_names)

        # Should contain both params
        assert "StoreId=6_" in key
        assert "UserId=123_" in key
        # Should end with hash
        assert len(key.split('_')[-1]) == 40

    def test_key_deterministic(self):
        """Test that same query generates same key."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]

        key1 = client.get_key_from_query(query, params, param_names)
        key2 = client.get_key_from_query(query, params, param_names)

        assert key1 == key2


class TestDataNormalization:
    """Test data normalization for JSON serialization."""

    def test_normalize_decimal(self):
        """Test Decimal conversion to float."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        row = {'id': 1, 'price': Decimal('19.99')}

        normalized = client._normalize_row(row)

        assert normalized['price'] == 19.99
        assert isinstance(normalized['price'], float)

    def test_normalize_datetime(self):
        """Test datetime conversion to ISO string."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        dt = datetime(2025, 12, 23, 10, 30, 0)
        row = {'id': 1, 'created_at': dt}

        normalized = client._normalize_row(row)

        assert isinstance(normalized['created_at'], str)
        assert normalized['created_at'] == '2025-12-23T10:30:00'

    def test_normalize_date(self):
        """Test date conversion to ISO string."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        d = date(2025, 12, 23)
        row = {'id': 1, 'birthday': d}

        normalized = client._normalize_row(row)

        assert isinstance(normalized['birthday'], str)
        assert normalized['birthday'] == '2025-12-23'

    def test_normalize_bytes(self):
        """Test bytes conversion to string."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        row = {'id': 1, 'data': b'test data'}

        normalized = client._normalize_row(row)

        assert normalized['data'] == 'test data'
        assert isinstance(normalized['data'], str)

    def test_normalize_none(self):
        """Test None values are preserved."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        row = {'id': 1, 'optional_field': None}

        normalized = client._normalize_row(row)

        assert normalized['optional_field'] is None


@pytest.mark.asyncio
class TestCacheOperations:
    """Test cache read/write operations."""

    async def test_write_and_read_cache(self):
        """Test writing to and reading from cache."""
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        client.redis_client = mock_redis

        # Write to cache
        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]
        test_data = [{'id': 123, 'name': 'Alice'}]

        await client.write_to_cache(query, test_data, params, param_names, ttl=3600)

        # Verify set was called with correct parameters
        assert mock_redis.set.called
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        assert key.startswith("UserId=123_")

        # Verify JSON serialization is compact (no spaces)
        json_value = call_args[0][1]
        assert ',' in json_value and ', ' not in json_value  # Compact format

        # Verify TTL has jitter (between 3240 and 3960)
        ttl = call_args[1]['ex']
        assert 3240 <= ttl <= 3960

    async def test_read_from_cache_hit(self):
        """Test cache hit returns cached data."""
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis client with cached data
        cached_data = [{'id': 123, 'name': 'Alice'}]
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data, separators=(',', ':')))
        client.redis_client = mock_redis

        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]

        result = await client.read_from_cache(query, params, param_names)

        assert result == cached_data
        assert mock_redis.get.called

    async def test_read_from_cache_miss(self):
        """Test cache miss returns None."""
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis client with no cached data
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        client.redis_client = mock_redis

        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]

        result = await client.read_from_cache(query, params, param_names)

        assert result is None

    async def test_with_cache_hit(self):
        """Test with_cache returns cached data on hit."""
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis client with cached data
        cached_data = {'result': 42}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data, separators=(',', ':')))
        client.redis_client = mock_redis

        # Function should not be called on cache hit
        async def expensive_function():
            raise Exception("Should not be called on cache hit!")

        query = "expensive_computation"
        result = await client.with_cache(expensive_function, query)

        assert result == cached_data
        assert mock_redis.get.called

    async def test_with_cache_miss(self):
        """Test with_cache executes function and caches result on miss."""
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis client with no cached data
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
        client.redis_client = mock_redis

        # Function to cache
        async def expensive_function():
            return {'result': 42}

        query = "expensive_computation"
        result = await client.with_cache(expensive_function, query)

        assert result == {'result': 42}
        assert mock_redis.get.called
        assert mock_redis.set.called

    async def test_with_cache_without_redis(self):
        """Test with_cache works without Redis (just executes function)."""
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, None)  # No Redis config

        # Function should be executed
        async def expensive_function():
            return {'result': 42}

        query = "expensive_computation"
        result = await client.with_cache(expensive_function, query)

        assert result == {'result': 42}


@pytest.mark.asyncio
class TestMRCServer:
    """Test MRCServer cache invalidation."""

    async def test_drop_outdated_cache_single_key(self):
        """Test dropping cache entries matching a single key pattern."""
        redis_config = {'host': 'localhost', 'port': 6379}
        server = MRCServer(redis_config)

        # Mock Redis client
        mock_redis = AsyncMock()
        # Simulate SCAN returning keys in two batches
        mock_redis.scan = AsyncMock(side_effect=[
            (1, [b'StoreId=6_abc123', b'UserId=123_def456', b'StoreId=6_ghi789']),
            (0, [b'UserId=999_jkl012'])  # cursor 0 means done
        ])
        mock_redis.delete = AsyncMock()
        server.redis_client = mock_redis

        count = await server.drop_outdated_cache(['StoreId'], [6])

        # Should delete 2 keys matching StoreId=6
        assert count == 2
        assert mock_redis.delete.call_count == 2

    async def test_drop_outdated_cache_multiple_keys(self):
        """Test dropping cache entries matching multiple key patterns."""
        redis_config = {'host': 'localhost', 'port': 6379}
        server = MRCServer(redis_config)

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=[
            (1, [b'StoreId=6_UserId=123_abc123', b'StoreId=6_UserId=456_def456', b'StoreId=7_UserId=123_ghi789']),
            (0, [b'UserId=999_jkl012'])
        ])
        mock_redis.delete = AsyncMock()
        server.redis_client = mock_redis

        # Should match BOTH StoreId=6 AND UserId=123 (AND logic)
        count = await server.drop_outdated_cache(['StoreId', 'UserId'], [6, 123])

        # Should delete only the key containing BOTH parameters
        assert count == 1

    async def test_drop_outdated_cache_no_matches(self):
        """Test dropping cache when no entries match."""
        redis_config = {'host': 'localhost', 'port': 6379}
        server = MRCServer(redis_config)

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=[
            (0, [b'UserId=999_abc123', b'UserId=888_def456'])
        ])
        mock_redis.delete = AsyncMock()
        server.redis_client = mock_redis

        count = await server.drop_outdated_cache(['StoreId'], [6])

        # Should delete no keys
        assert count == 0
        assert not mock_redis.delete.called


@pytest.mark.asyncio
class TestContextManagers:
    """Test async context manager support."""

    async def test_client_context_manager(self):
        """Test MRCClient as async context manager."""
        mysql_config = {'host': 'localhost', 'db': 'test'}
        redis_config = {'host': 'localhost', 'port': 6379}

        # Should not raise any exceptions
        async with MRCClient(mysql_config, redis_config) as client:
            assert client is not None
            assert isinstance(client, MRCClient)

    async def test_server_context_manager(self):
        """Test MRCServer as async context manager."""
        redis_config = {'host': 'localhost', 'port': 6379}

        # Should not raise any exceptions
        async with MRCServer(redis_config) as server:
            assert server is not None
            assert isinstance(server, MRCServer)


class TestConnectionStringParsing:
    """Test MySQL connection string parsing."""

    def test_parse_full_connection_string(self):
        """Test parsing complete connection string."""
        client = MRCClient('mysql://user:pass@localhost:3306/testdb')

        config = client._parse_connection_string('mysql://user:pass@localhost:3306/testdb')

        assert config['host'] == 'localhost'
        assert config['port'] == 3306
        assert config['user'] == 'user'
        assert config['password'] == 'pass'
        assert config['db'] == 'testdb'

    def test_parse_connection_string_defaults(self):
        """Test parsing connection string with defaults."""
        client = MRCClient('mysql://user@localhost/testdb')

        config = client._parse_connection_string('mysql://user@localhost/testdb')

        assert config['host'] == 'localhost'
        assert config['port'] == 3306  # Default
        assert config['user'] == 'user'
        assert config['password'] == ''  # Default
        assert config['db'] == 'testdb'


@pytest.mark.asyncio
class TestRedisConnectionURL:
    """Test Redis URL connection string support."""

    async def test_redis_url_connection(self):
        """Test Redis connection using URL format."""
        mysql_config = {'host': 'localhost', 'db': 'test'}
        redis_url = "redis://localhost:6379?decode_responses=True&health_check_interval=2"
        
        client = MRCClient(mysql_config, redis_url)
        
        # Call _connect_redis to ensure it handles URL format
        await client._connect_redis()
        
        # Verify redis_client is created (even if connection fails, the from_url should be called)
        # In a real test environment with Redis running, this would succeed
        assert client.redis_config == redis_url
        
        # Cleanup
        await client.close_redis_connection()

    async def test_redis_dict_connection(self):
        """Test Redis connection using dictionary format still works."""
        mysql_config = {'host': 'localhost', 'db': 'test'}
        redis_config = {'host': 'localhost', 'port': 6379, 'decode_responses': True}
        
        client = MRCClient(mysql_config, redis_config)
        
        # Mock Redis client to avoid actual connection
        mock_redis = AsyncMock()
        client.redis_client = mock_redis
        
        # Verify dict config is stored correctly
        assert client.redis_config == redis_config


class TestJSONSerialization:
    """Test JSON serialization compatibility with TypeScript."""

    def test_json_compact_format(self):
        """Test JSON is serialized in compact format (no spaces)."""
        data = [{'id': 1, 'name': 'Alice', 'scores': [95, 87, 92]}]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Should not contain spaces after commas or colons
        assert ', ' not in json_str
        assert ': ' not in json_str
        # Should be valid JSON
        assert json.loads(json_str) == data

    def test_json_decimal_handling(self):
        """Test Decimal values are converted before JSON serialization."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        row = {'id': 1, 'price': Decimal('19.99')}

        normalized = client._normalize_row(row)
        json_str = json.dumps(normalized, separators=(',', ':'))

        # Should serialize successfully
        parsed = json.loads(json_str)
        assert parsed['price'] == 19.99
