"""Interoperability tests to ensure Python and TypeScript implementations are compatible.

CRITICAL: These tests verify that cache data written by one implementation
can be read by the other. This ensures both implementations can share the same Redis cache.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from mysql_redis_cache import MRCClient

pytestmark = pytest.mark.unit


class TestCacheKeyCompatibility:
    """Test cache key generation matches TypeScript exactly."""

    def test_key_generation_matches_typescript_no_params(self):
        """Verify Python generates same cache key as TypeScript for query without params.
        
        TypeScript: crypto.createHash('sha1').update(query).digest('hex')
        Python: hashlib.sha1(query.encode('utf-8')).hexdigest()
        """
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users"

        # Generate key
        python_key = client.get_key_from_query(query)

        # Expected TypeScript key (SHA1 of query)
        expected_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()

        assert python_key == expected_hash
        assert len(python_key) == 40

    def test_key_generation_matches_typescript_with_params(self):
        """Verify Python generates same cache key as TypeScript with parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]

        # Generate key
        python_key = client.get_key_from_query(query, params, param_names)

        # Expected format: "UserId=123_{hash}"
        query_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()
        expected_key = f"UserId=123_{query_hash}"

        assert python_key == expected_key

    def test_key_generation_multiple_params(self):
        """Verify cache key with multiple parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM orders WHERE store_id = ? AND user_id = ?"
        params = [6, 123]
        param_names = ["StoreId", "UserId"]

        python_key = client.get_key_from_query(query, params, param_names)

        # Expected format: "StoreId=6_UserId=123_{hash}"
        query_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()
        expected_key = f"StoreId=6_UserId=123_{query_hash}"

        assert python_key == expected_key

    def test_key_generation_with_string_params(self):
        """Verify cache key with string parameters."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})
        query = "SELECT * FROM users WHERE email = ?"
        params = ["alice@example.com"]
        param_names = ["Email"]

        python_key = client.get_key_from_query(query, params, param_names)

        query_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()
        expected_key = f"Email=alice@example.com_{query_hash}"

        assert python_key == expected_key


class TestJSONSerializationCompatibility:
    """Test JSON serialization matches TypeScript JSON.stringify()."""

    def test_compact_json_format(self):
        """Verify JSON has no spaces (compact format like TypeScript)."""
        data = [{"id": 1, "name": "Alice"}]

        # Python serialization
        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Should match TypeScript: JSON.stringify(data)
        # TypeScript produces: [{"id":1,"name":"Alice"}]
        expected = '[{"id":1,"name":"Alice"}]'

        assert json_str == expected
        assert ', ' not in json_str
        assert ': ' not in json_str

    def test_nested_objects_and_arrays(self):
        """Verify nested structures serialize correctly."""
        data = [
            {
                "id": 1,
                "name": "Alice",
                "tags": ["admin", "user"],
                "metadata": {"role": "admin", "active": True}
            }
        ]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Verify it's compact and parseable
        assert ', ' not in json_str
        parsed = json.loads(json_str)
        assert parsed == data

    def test_null_values(self):
        """Verify None/null compatibility."""
        data = [{"id": 1, "optional": None}]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Python None should serialize to JSON null
        assert '"optional":null' in json_str
        parsed = json.loads(json_str)
        assert parsed[0]["optional"] is None

    def test_boolean_values(self):
        """Verify boolean compatibility."""
        data = [{"id": 1, "active": True, "deleted": False}]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Python True/False should serialize to JSON true/false
        assert '"active":true' in json_str
        assert '"deleted":false' in json_str

    def test_numeric_values(self):
        """Verify numeric types serialize correctly."""
        data = [{"int": 42, "float": 3.14, "zero": 0, "negative": -10}]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        parsed = json.loads(json_str)
        assert parsed[0]["int"] == 42
        assert parsed[0]["float"] == 3.14
        assert parsed[0]["zero"] == 0
        assert parsed[0]["negative"] == -10

    def test_unicode_characters(self):
        """Verify Unicode handling with ensure_ascii=False."""
        data = [{"name": "José", "city": "São Paulo", "emoji": "🚀"}]

        json_str = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

        # Should contain actual Unicode characters, not escaped
        assert 'José' in json_str
        assert 'São Paulo' in json_str
        assert '🚀' in json_str

        parsed = json.loads(json_str)
        assert parsed[0]["name"] == "José"


class TestMySQLDataTypeCompatibility:
    """Test MySQL data type handling for cross-platform compatibility."""

    def test_decimal_to_float_conversion(self):
        """Test Decimal columns convert to float (matching TypeScript number)."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})

        # Simulate MySQL row with DECIMAL column
        row = {'id': 1, 'price': Decimal('19.99'), 'tax': Decimal('1.50')}

        normalized = client._normalize_row(row)

        # Should be converted to float
        assert isinstance(normalized['price'], float)
        assert isinstance(normalized['tax'], float)
        assert normalized['price'] == 19.99
        assert normalized['tax'] == 1.50

        # Should serialize to JSON correctly
        json_str = json.dumps(normalized, separators=(',', ':'))
        parsed = json.loads(json_str)
        assert parsed['price'] == 19.99

    def test_datetime_to_iso_string(self):
        """Test DATETIME columns convert to ISO string."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})

        # Simulate MySQL row with DATETIME column
        dt = datetime(2025, 12, 23, 10, 30, 0)
        row = {'id': 1, 'created_at': dt}

        normalized = client._normalize_row(row)

        # Should be converted to ISO string
        assert isinstance(normalized['created_at'], str)
        assert normalized['created_at'] == '2025-12-23T10:30:00'

        # Should serialize to JSON correctly
        json_str = json.dumps(normalized, separators=(',', ':'))
        assert '"created_at":"2025-12-23T10:30:00"' in json_str

    def test_date_to_iso_string(self):
        """Test DATE columns convert to ISO string."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})

        # Simulate MySQL row with DATE column
        d = date(2025, 12, 23)
        row = {'id': 1, 'birthday': d}

        normalized = client._normalize_row(row)

        # Should be converted to ISO string
        assert isinstance(normalized['birthday'], str)
        assert normalized['birthday'] == '2025-12-23'

    def test_mixed_data_types(self):
        """Test row with multiple MySQL data types."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})

        # Simulate complex MySQL row
        row = {
            'id': 1,
            'name': 'Alice',
            'price': Decimal('99.95'),
            'created_at': datetime(2025, 12, 23, 15, 45, 30),
            'birthday': date(1990, 5, 15),
            'active': True,
            'notes': None,
            'tags': '["admin","user"]',  # JSON stored as string in MySQL
        }

        normalized = client._normalize_row(row)

        # Verify all conversions
        assert normalized['id'] == 1
        assert normalized['name'] == 'Alice'
        assert isinstance(normalized['price'], float)
        assert normalized['price'] == 99.95
        assert normalized['created_at'] == '2025-12-23T15:45:30'
        assert normalized['birthday'] == '1990-05-15'
        assert normalized['active'] is True
        assert normalized['notes'] is None
        assert normalized['tags'] == '["admin","user"]'

        # Should serialize successfully
        json_str = json.dumps(normalized, separators=(',', ':'), ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed == normalized


class TestQueryResultSerialization:
    """Test complete query result serialization."""

    def test_serialize_query_result(self):
        """Test full query result array serialization."""
        client = MRCClient({'host': 'localhost', 'db': 'test'})

        # Simulate query result with multiple rows
        rows = [
            {'id': 1, 'name': 'Alice', 'score': Decimal('95.5')},
            {'id': 2, 'name': 'Bob', 'score': Decimal('87.0')},
            {'id': 3, 'name': 'Charlie', 'score': None},
        ]

        # Normalize all rows
        normalized_rows = [client._normalize_row(row) for row in rows]

        # Serialize
        json_str = json.dumps(normalized_rows, separators=(',', ':'), ensure_ascii=False)

        # Verify format
        assert json_str.startswith('[')
        assert json_str.endswith(']')
        assert ', ' not in json_str  # Compact format

        # Verify parseability
        parsed = json.loads(json_str)
        assert len(parsed) == 3
        assert parsed[0]['score'] == 95.5
        assert parsed[1]['score'] == 87.0
        assert parsed[2]['score'] is None

    def test_empty_result_set(self):
        """Test empty query result serialization."""
        rows = []

        json_str = json.dumps(rows, separators=(',', ':'), ensure_ascii=False)

        assert json_str == '[]'
        parsed = json.loads(json_str)
        assert parsed == []


@pytest.mark.asyncio
class TestCrossLanguageCompatibility:
    """Integration tests for cross-language cache compatibility.
    
    These tests verify that data cached by Python can be read correctly
    when deserialized, matching what TypeScript would produce.
    """

    async def test_cache_key_and_data_format(self):
        """Test complete cache workflow matches TypeScript format."""
        from unittest.mock import AsyncMock

        redis_config = {'host': 'localhost', 'port': 6379}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = AsyncMock(side_effect=mock_set)
        mock_redis.get = AsyncMock(side_effect=mock_get)
        client.redis_client = mock_redis

        # Write data
        query = "SELECT * FROM users WHERE id = ?"
        params = [123]
        param_names = ["UserId"]
        data = [{'id': 123, 'name': 'Alice', 'score': 95.5}]

        await client.write_to_cache(query, data, params, param_names, ttl=3600)

        # Read it back
        cached = await client.read_from_cache(query, params, param_names)

        # Should match exactly
        assert cached == data

    async def test_complex_data_round_trip(self):
        """Test complex data structures survive round trip through cache."""
        from unittest.mock import AsyncMock

        redis_config = {'host': 'localhost', 'port': 6379}
        mysql_config = {'host': 'localhost', 'db': 'test'}

        client = MRCClient(mysql_config, redis_config)

        # Mock Redis
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = AsyncMock(side_effect=mock_set)
        mock_redis.get = AsyncMock(side_effect=mock_get)
        client.redis_client = mock_redis

        # Complex data
        query = "SELECT * FROM complex_table"
        data = [
            {
                "id": 1,
                "name": "Alice",
                "scores": [95, 87, 92],
                "metadata": {"role": "admin", "active": True},
                "optional": None,
            },
            {
                "id": 2,
                "name": "Bob",
                "scores": [],
                "metadata": {"role": "user", "active": False},
                "optional": "value",
            },
        ]

        await client.write_to_cache(query, data, [], [], ttl=3600)
        cached = await client.read_from_cache(query, [], [])

        # Should match exactly
        assert cached is not None
        assert cached == data
        assert cached[0]["scores"] == [95, 87, 92]
        assert cached[0]["metadata"]["active"] is True
        assert cached[0]["optional"] is None
        assert cached[1]["metadata"]["active"] is False


class TestHashEncoding:
    """Test SHA1 hash encoding matches TypeScript."""

    def test_sha1_encoding_utf8(self):
        """Verify SHA1 uses UTF-8 encoding like TypeScript."""
        query = "SELECT * FROM users WHERE name = 'José'"

        # Python implementation
        python_hash = hashlib.sha1(query.encode('utf-8')).hexdigest()

        # Should be 40 character hex string
        assert len(python_hash) == 40
        assert all(c in '0123456789abcdef' for c in python_hash)

        # Verify consistent encoding
        hash1 = hashlib.sha1(query.encode('utf-8')).hexdigest()
        hash2 = hashlib.sha1(query.encode('utf-8')).hexdigest()
        assert hash1 == hash2

    def test_sha1_different_queries_different_hashes(self):
        """Verify different queries produce different hashes."""
        query1 = "SELECT * FROM users"
        query2 = "SELECT * FROM orders"

        hash1 = hashlib.sha1(query1.encode('utf-8')).hexdigest()
        hash2 = hashlib.sha1(query2.encode('utf-8')).hexdigest()

        assert hash1 != hash2

    def test_sha1_whitespace_sensitive(self):
        """Verify hash is sensitive to whitespace (as it should be)."""
        query1 = "SELECT * FROM users"
        query2 = "SELECT  *  FROM  users"  # Extra spaces

        hash1 = hashlib.sha1(query1.encode('utf-8')).hexdigest()
        hash2 = hashlib.sha1(query2.encode('utf-8')).hexdigest()

        # Different whitespace should produce different hashes
        assert hash1 != hash2
