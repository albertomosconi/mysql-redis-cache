# Python Migration Plan - MySQL-Redis-Cache

**Date:** December 23, 2025  
**Target:** Python 3.13+ with full async support  
**Package Manager:** uv  

## Overview

Migrate the TypeScript `@actvalue/mysql-redis-cache` library to Python, maintaining feature parity and API similarity while following Python best practices.

---

## Project Configuration

### Package Details
- **PyPI Name:** `actvalue.mysql-redis-cache`
- **Import Name:** `mysql_redis_cache` (namespace-free for simplicity)
- **Import Style:** `from mysql_redis_cache import MRCClient, MRCServer`
- **Classes:** `MRCClient`, `MRCServer` (matching TypeScript)
- **License:** MIT
- **Python Version:** >=3.13

### Dependencies
**Core:**
- `aiomysql` - Async MySQL driver (AWS Lambda compatible, PyMySQL protocol)
- `redis[asyncio]` - Redis client with async support

**Development:**
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `ruff` - Linting and formatting

---

## Project Structure

```
/
├── README.md                        # Global repo README (new)
├── Makefile                         # Build/test/publish commands (new)
├── .gitignore                       # Git ignore (add Python/.venv/)
├── redis-compose.yml                # Shared Docker Compose (moved from Typescript/tests/)
├── Typescript/                      # Existing implementation
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── README.md
└── Python/                          # New Python implementation
    ├── pyproject.toml              # Project configuration (uv managed)
    ├── README.md                   # Python-specific documentation
    ├── .python-version             # 3.13
    ├── uv.lock                     # Dependency lock file (uv managed)
    ├── .venv/                      # Virtual environment (gitignored, created by uv sync)
    ├── src/
    │   └── mysql_redis_cache/
    │       ├── __init__.py         # Public exports
    │       ├── client.py           # MRCClient implementation
    │       ├── server.py           # MRCServer implementation
    │       └── py.typed            # PEP 561 type marker
    └── tests/
        ├── __init__.py
        ├── test_cache.py           # Core caching functionality tests
        ├── test_interop_unit.py    # Cross-platform compatibility unit tests
        ├── test_interop_e2e.py     # Cross-platform E2E tests
        └── test_mysql.py           # MySQL integration tests
```

---

## Implementation Details

### 1. MRCClient Class (`client.py`)

**Purpose:** Execute MySQL queries with Redis caching

**Attributes:**
- `mysql_pool: Optional[aiomysql.Pool]` - MySQL connection pool
- `mysql_config: Union[Dict, str]` - MySQL configuration or connection string
- `redis_config: Optional[Dict]` - Redis configuration
- `redis_client: Optional[redis.asyncio.Redis]` - Redis client instance

**Methods:**

```python
async def __init__(mysql_config: Union[Dict[str, Any], str], 
                   redis_config: Optional[Dict[str, Any]] = None)
    """Initialize client with MySQL and optional Redis config."""

async def __aenter__() -> 'MRCClient'
    """Context manager entry - connect to services."""

async def __aexit__(exc_type, exc_val, exc_tb)
    """Context manager exit - cleanup connections."""

async def _connect_mysql() -> None
    """Create MySQL connection pool using aiomysql.create_pool()."""

async def _connect_redis() -> None
    """Connect to Redis using redis.asyncio.Redis()."""

async def close_redis_connection() -> None
    """Close Redis connection gracefully."""

def get_mysql_pool() -> aiomysql.Pool
    """Return MySQL pool for direct database access."""

async def query_to_promise(query: str, params: Optional[List[Any]] = None) -> Any
    """Execute MySQL query and return results."""

def get_key_from_query(query: str, 
                       params: Optional[List[Any]] = None,
                       param_names: List[str] = []) -> str
    """Generate cache key using SHA1(query) + param_names=param_values."""

async def read_from_cache(query: str,
                          params: Optional[List[Any]] = None,
                          param_names: List[str] = []) -> Optional[Any]
    """Read cached query result from Redis. Returns None if not found."""

async def write_to_cache(query: str,
                         value: Any,
                         params: Optional[List[Any]] = None,
                         param_names: List[str] = [],
                         ttl: int = 86400) -> None
    """Write query result to cache with TTL jitter (±10%)."""

async def with_cache(fn: Callable[[], Awaitable[Any]],
                     query: str,
                     params: Optional[List[Any]] = None,
                     param_names: List[str] = [],
                     ttl: int = 86400) -> Any
    """Execute arbitrary async function with caching. CRITICAL FEATURE."""

async def query_with_cache(query: str,
                           params: Optional[List[Any]] = None,
                           param_names: List[str] = [],
                           ttl: int = 86400) -> Any
    """Execute MySQL query with caching. Main convenience method."""
```

**Key Implementation Notes:**
- **Cache Key Format:** `{param_name1}={value1}_{param_name2}={value2}_{SHA1_hash}`
- **TTL Jitter:** `ttl + round(ttl * random.uniform(-0.1, 0.1))` to prevent thundering herd
- **JSON Serialization:** **CRITICAL:** Use `json.dumps(value, separators=(',', ':'), ensure_ascii=False)` to match TypeScript's `JSON.stringify()`
- **Hash Encoding:** Use UTF-8: `hashlib.sha1(query.encode('utf-8')).hexdigest()`
- **Decimal Handling:** Convert `Decimal` to `float` before JSON serialization
- **DateTime Handling:** Convert to ISO 8601 string format
- **Error Handling:** Raise exceptions (ConnectionError, ValueError, etc.)
- **Lazy Connection:** Connect only when first method is called
- **Type Hints:** Full type annotations using `typing` module

### 2. MRCServer Class (`server.py`)

**Purpose:** Manage cache invalidation

**Attributes:**
- `redis_config: Dict[str, Any]` - Redis configuration
- `redis_client: Optional[redis.asyncio.Redis]` - Redis client instance

**Methods:**

```python
async def __init__(redis_config: Dict[str, Any])
    """Initialize server with Redis configuration."""

async def __aenter__() -> 'MRCServer'
    """Context manager entry."""

async def __aexit__(exc_type, exc_val, exc_tb)
    """Context manager exit."""

async def _connect_redis() -> None
    """Connect to Redis."""

async def close_redis_connection() -> None
    """Close Redis connection."""

async def drop_outdated_cache(key_names: List[str], 
                              key_values: List[Any]) -> int
    """Delete all cached queries matching the given key patterns.
    
    Uses Redis SCAN to iterate all keys, builds regex from key_names/key_values,
    deletes matching entries. Returns count of deleted keys.
    
    Example:
        await server.drop_outdated_cache(['StoreId'], [6])
        Deletes all cache entries containing 'StoreId=6'
    """
```

**Key Implementation Notes:**
- **Pattern Matching:** Build regex: `StoreId=6|UserId=123` for multiple keys
- **Redis SCAN:** Use cursor-based iteration (not KEYS) for production safety
- **Regex Matching:** Use Python `re` module for pattern matching
- **Return Value:** Count of deleted entries

---

## Configuration Formats

### MySQL Configuration

**Option 1: Dictionary**
```python
mysql_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'myuser',
    'password': 'mypassword',
    'db': 'mydatabase',
    'minsize': 1,
    'maxsize': 10,
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

---

## Testing Strategy

### Test Files

**`tests/test_cache.py`** - Core functionality (minimal but comprehensive)
- Test cache hit/miss behavior
- Test TTL expiration
- Test `with_cache()` with arbitrary functions
- Test cache key generation
- Test write/read cache operations
- Test `drop_outdated_cache()`
- Mock MySQL connection to focus on caching logic

**`tests/test_mysql.py`** - MySQL integration (optional, document only)
- Test query_to_promise with real database
- Test connection string support
- Test parameterized queries
- Requires MySQL instance (document setup, don't run in CI)

**`tests/test_interop.py`** - Cross-platform interoperability (CRITICAL)
- Test cache key generation matches TypeScript exactly
- Test Python writes cache, read from TypeScript test
- Test TypeScript writes cache, read from Python
- Test various data types (strings, numbers, nulls, arrays, objects)
- Test parameter ordering and naming
- Verify JSON serialization compatibility

### Docker Compose Setup

**Move `redis-compose.yml` to repository root:**
```yaml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --requirepass testpassword
```

**Run interoperability tests
make test-interop

# Stop Redis
docker-compose -f redis-compose.yml down --volumes
```

---

## Cross-Platform Interoperability (CRITICAL REQUIREMENT)

### Use Case: SQL Query Result Caching

**Requirement:** SQL query results cached by TypeScript must be readable by Python and vice versa.

**Simplified Scope:** Since we're only caching SQL query results (not arbitrary objects), we only need to handle:
- Arrays of row objects (query results)
- Standard MySQL data types
- Query metadata (if any)

**Key Compatibility Points:**

1. **Cache Key Generation (MUST BE IDENTICAL)**
   ```
   Format: {param_name1}={value1}_{param_name2}={value2}_{SHA1_hash}
   
   Examples:
   - No params: "{SHA1_hash}"
   - With params: "UserId=123_StoreId=456_{SHA1_hash}"
   
   TypeScript: crypto.createHash('sha1').update(query).digest('hex')
   Python:    hashlib.sha1(query.encode('utf-8')).hexdigest()
   ```

2. **JSON Serialization of Query Results (MUST MATCH)**
   - TypeScript: `JSON.stringify(rows)` produces compact JSON
   - Python: Use `json.dumps(rows, separators=(',', ':'), ensure_ascii=False, default=str)`
   - **Important:** Use `separators=(',', ':')` to match JS compact format (no spaces)
   - **Character Encoding:** UTF-8 for both platforms

3. **MySQL Data Type Handling**
   
   Query results are arrays of row objects. Each row is a dictionary/object with column names as keys.
   
   | MySQL Type | TypeScript (mysql2) | Python (aiomysql) | JSON Storage | Notes |
   |------------|---------------------|-------------------|--------------|-------|
   | INT/BIGINT | number | int | number | Direct mapping |
   | VARCHAR/TEXT | string | str | string | Direct mapping |
   | DECIMAL/NUMERIC | number/string | Decimal | number | Convert Decimal to float in Python |
   | DATETIME/TIMESTAMP | Date object or string | datetime or string | string | aiomysql can return as string directly |
   | DATE | string | date or string | string | Usually string format |
   | NULL | null | None | null | Direct mapping |
   | JSON | object | dict | object | mysql2 auto-parses, aiomysql may return string |
   | BOOLEAN/TINYINT(1) | boolean/number | int | number | 0/1 values |
Query Result Processing:**
```python
import json
from decimal import Decimal
from datetime import datetime, date

def normalize_row(row: dict) -> dict:
    """Normalize a database row for JSON serialization compatibility with TypeScript"""
    normalized = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            # Convert Decimal to float (matches TypeScript number)
            normalized[key] = float(value)
        elif isinstance(value, (datetime, date)):
            # Convert to ISO string if not already a string
            normalized[key] = value.isoformat() if hasattr(value, 'isoformat') else str(value)
        elif isinstance(value, bytes):
            # Convert bytes to base64 or hex string (rare for standard queries)
            normalized[key] = value.decode('utf-8', errors='ignore')
        else:
            # int, str, None, bool, dict, list - pass through
            normalized[key] = value
    return normalized

def serialize_query_result(rows: list) -> str:
    """Serialize query results to match TypeScript JSON.stringify()"""
    # Normalize all rows first
    normalized_rows = [normalize_row(row) for row in rows]
    # Use compact JSON format (no spaces) to match JavaScript
    return json.dumps(normalized_rows, separators=(',', ':'), ensure_ascii=False)

def deserialize_query_result(cached_data: str) -> list:
    """Deserialize cached query results"""
    return json.loads(cached_data)
```

**Key Points:**
- aiomysql with `cursorclass=aiomysql.DictCursor` returns list of dictionaries
- Convert Decimal to float before serialization
- Handle datetime objects (convert to string if needed, but aiomysql often returns strings)
- Use `separators=(',', ':')` for compact JSON matching TypeScript
- No special handling needed for None (→ null), int, str, boolecimal Handling:**
```python
from decimal import Decimal

# aiomysql returns Decimal for DECIMAL columns
# Convert to float for JSON compatibility
result = [{k: float(v) if isinstance(v, Decimal) else v 
           for k, v in row.items()} for row in rows]
```

### Interoperability Testing Strategy

**Test Approach:**
1. Write integration test that runs both TypeScript and Python code
2. Share Redis instance between tests
3. Verify cache key generation matches exactly
4. Test write-read cycle in both directions

**Test Cases:**

```python
# Test 1: Key generation compatibility
def test_key_generation_matches_typescript():
    """Verify Python generates same cache keys as TypeScript"""
    query = "SELECT * FROM users WHERE id = ?"
    params = [123]
    param_names = ["UserId"]
    
    expected_key = "UserId=123_<sha1_hash>"  # From TS test
    python_key = client.get_key_from_query(query, params, param_names)
    
    assert python_key == expected_key

# Test 2: Write in Python, read in TypeScript
async def test_python_write_typescript_read():
    """Write cache in Python, verify TypeScript can read it"""
    # Python writes
    await python_client.write_to_cache(query, result, params, param_names)
    
    # TypeScript reads (run via subprocess or separate test)
    # Verify result matches

# Test 3: Write in TypeScript, read in Python
async def test_typescript_write_python_read():
    """Write cache in TypeScript, verify Python can read it"""
    # TypeScript writes (run first)
    # Python reads
    cached = await python_client.read_from_cache(query, params, param_names)
    
    assert cached == expected_result

# Test 4: Complex data types
async def test_complex_types_interop():
    """Test arrays, objects, nulls, numbers, strings"""
    test_data = [
        {"id": 1, "name": "Alice", "score": 95.5, "tags": ["admin", "user"]},
        {"id": 2, "name": "Bob", "score": None, "tags": []},
    ]
    
    # Write in one language, read in other
    # Verify exact match
```

**Makefile Test Command:**
```makefile
test-interop:
	docker-compose -f redis-compose.yml up -d
	cd Typescript && npm test -- tests/interop.test.ts
	cd Python && uv run pytest tests/test_interop.py -v
	docker-compose -f redis-compose.yml down --volumes
```

### Potential Compatibility Issues & Solutions

| Issue | Solution |
|-------|----------|
| Decimal vs float | Convert Python Decimal to float before JSON serialization |
| DateTime objects | aiomysql can return strings directly (preferred), or convert to ISO 8601 |
| Unicode handling | Use UTF-8 everywhere, `ensure_ascii=False` in Python |
| Number formatting | Use compact JSON `separators=(',', ':')` (no spaces) |
| Hash encoding | UTF-8 encode query string: `query.encode('utf-8')` |
| NULL values | Python None ↔ JS null (automatic in JSON) |
| Boolean/TINYINT(1) | Both return as number (0/1), compatible |

### Validation Checklist

- [ ] Cache keys generated by Python match TypeScript exactly
- [ ] SQL query results serialize to identical JSON format
- [ ] TypeScript can read Python-cached SQL results
- [ ] Python can read TypeScript-cached SQL results
- [ ] Decimal columns handled correctly (converted to float)
- [ ] NULL values preserved correctly
- [ ] DateTime/Date columns compatible (prefer string format)
- [ ] TTL behavior identical in both implementations
- [ ] Cache invalidation works across both platformstart Redis
docker-compose -f redis-compose.yml up -d

# Run tests
make test

# Stop Redis
docker-compose -f redis-compose.yml down --volumes
```

---

## Makefile (Root Level)

Based on https://github.com/pmosconi/view-arc pattern:

```makefile
.PHONY: help install-ts install-py test-ts test-py lint-ts lint-py build-ts build-py publish-ts publish-py clean

help:
	@echo "Available commands:"
	@echo "  make install-ts    - Install TypeScript dependencies"
	@echo "  make install-py    - Install Python dependencies"
	@echo "  make test-ts       - Run TypeScript tests"
	@echo "  make test-py       - Run Python tests"
	@echo "  make lint-ts       - Lint TypeScript code"
	@echo "  make lint-py       - Lint Python code"
	@echo "  make build-ts      - Build TypeScript package"
	@echo "  make build-py      - Build Python package"
	@echo "  make publish-ts    - Publish TypeScript to npm"
	@echo "  make publish-py    - Publish Python to PyPI"
	@echo "  make clean         - Clean build artifacts"

# TypeScript commands
install-ts:
	cd Typescript && npm install

test-ts:
	cd Typescript && npm test

lint-ts:
	cd Typescript && npm run lint

build-ts:
	cd Typescript && npm run build

publish-ts:
	cd Typescript && npm publish

# Python commands
install-py:
	@echo "Setting up Python environment with uv..."
	cd Python && uv sync
	@echo "Virtual environment created at Python/.venv/"

test-py:
	cd Python && uv run pytest

lint-py:
	cd Python && uv run ruff check src tests
	cd Python && uv run ruff format --check src tests

format-py:
	cd Python && uv run ruff format src tests

build-py:
	cd Python && uv build

publish-py:
	cd Python && uv publish

# Utility commands
venv-py:
	@echo "Virtual environment location:"
	@cd Python && uv run python -c "import sys; print(sys.prefix)"

# Combined commands
install: install-ts install-py
test-interop:
	@echo "Starting Redis for interop tests..."
	docker-compose -f redis-compose.yml up -d
	@echo "Running TypeScript interop tests..."
	cd Typescript && npm run test -- tests/interop.test.ts || true
	@echo "Running Python interop tests..."
	cd Python && uv run pytest tests/test_interop.py -v
	@echo "Stopping Redis..."
	docker-compose -f redis-compose.yml down --volumes


test: test-ts test-py

clean:
	rm -rf Typescript/dist Typescript/coverage
	rm -rf Python/dist Python/.pytest_cache Python/src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
```

---

## Project Initialization with uv

### Initial Setup Commands

```bash
# Navigate to repo root
cd /Users/paolomosconi/Source/Repos/mysql-redis-cache

# Create Python directory
mkdir -p Python
cd Python

# Initialize uv project
uv init --lib --name mysql-redis-cache

# Set Python version
echo "3.13" > .python-version

# Create/sync virtual environment with dependencies
uv sync

# Verify setup
uv run python --version  # Should show Python 3.13.x
```

**Note:** `uv` automatically manages the virtual environment:
- First `uv sync` creates `.venv/` directory
- No need to manually activate - `uv run` uses the venv automatically
- Virtual environment is stored in `Python/.venv/`

---

## pyproject.toml Configuration

```toml
[project]
name = "actvalue.mysql-redis-cache"
version = "0.1.0"
description = "Async wrapper for MySQL queries with Redis caching"
authors = [
    {name = "ActValue", email = "your-email@example.com"}
]
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.13"
keywords = ["mysql", "redis", "cache", "async", "database"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.13",
    "Topic :: Database",
    "Topic :: Software Development :: Libraries :: Python Modules",
]

dependencies = [
    "aiomysql>=0.2.0",
    "redis[asyncio]>=5.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.7.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/mysql-redis-cache"
Repository = "https://github.com/yourusername/mysql-redis-cache"
Issues = "https://github.com/yourusername/mysql-redis-cache/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/mysql_redis_cache"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --cov=mysql_redis_cache --cov-report=term-missing"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
ignore = []

[tool.coverage.run]
source = ["src"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

---

## README Files

### Global README.md (Root)

```markdown
# MySQL-Redis-Cache

Wrapper for MySQL queries with Redis caching, available for both TypeScript and Python.

## Features

- 🚀 Async/await interop.py (CRITICAL)
  - [ ] Test cache key generation matches TypeScript
  - [ ] Test Python write → TypeScript read
  - [ ] Test TypeScript write → Python read
  - [ ] Test complex data types (arrays, objects, nulls)
  - [ ] Test decimal/float handling
  - [ ] Test datetime serialization
- [ ] Add TypeScript interop test (Typescript/tests/interop.test.ts)
  - [ ] Write test data to cache
  - [ ] Verify Python can read it
- [ ] Write test_mysql.py (optional integration tests)
- [ ] Verify test coverage >80%
- [ ] **Run full interop test suite to validate compatibility**hing with Redis
- ⏱️ Configurable TTL with jitter to prevent thundering herd
- 🔑 Smart cache key generation from query and parameters
- 🧹 Selective cache invalidation
- 📦 Connection pooling for MySQL
- 🔧 Support for arbitrary function caching

## Implementations

### TypeScript / Node.js
📖 [TypeScript Documentation](./Typescript/README.md)

```bash
npm install @actvalue/mysql-redis-cache
```

### Python
📖 [Python Documentation](./Python/README.md)

## Cache Format Compatibility (CRITICAL)

**Both implementations MUST:**
- Generate identical cache keys for same query/params
- Use identical JSON serialization format
- Store data in Redis with same structure
- Handle all MySQL data types consistently


## Development Setup

```bash
# Clone repository
git clone <repo-url>
cd mysql-redis-cache/Python

# uv automatically creates and manages virtual environment
uv sync

# Run tests (uv handles venv activation automatically)
uv run pytest

# The virtual environment is created at .venv/ but you don't need to activate it manually
# All uv run commands automatically use the virtual environment
```
**This ensures:**
- Python can read cache written by TypeScript
- TypeScript can read cache written by Python
- Shared cache works transparently across both platforms
- No data corruption or type mismatch issues

```bash
pip install actvalue.mysql-redis-cache
```

## License

MIT
```

### Python/README.md

```markdown
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
async def expensive_computation(x: int, y: int) -> int:
    # Some expensive operation
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

## API Reference

See inline documentation for detailed API information.

## Requirements

- Python 3.13+
- aiomysql
- redis

## License

MIT
```

---

## Implementation Checklist

### Phase 1: Project Setup
- [ ] Create Python directory structure
- [ ] Initialize uv project: `cd Python && uv init --lib`
- [ ] Set up pyproject.toml with uv
- [ ] Create .python-version file (3.13)
- [ ] Create virtual environment: `uv venv --python 3.13` (or let `uv sync` handle it)
- [ ] Install dependencies: `uv sync`
- [ ] Initialize package with __init__.py
- [ ] Add py.typed marker
- [ ] Create root Makefile
- [ ] Move redis-compose.yml to root
- [ ] Create global README.md

### Phase 2: Core Implementation
- [ ] Implement MRCClient class
  - [ ] Constructor with config parsing
  - [ ] MySQL connection handling (aiomysql)
  - [ ] Redis connection handling (redis.asyncio)
  - [ ] Context manager support
  - [ ] get_key_from_query() with SHA1
  - [ ] query_to_promise()
  - [ ] read_from_cache()
  - [ ] write_to_cache() with TTL jitter
  - [ ] with_cache() for arbitrary functions
  - [ ] query_with_cache()
  - [ ] Connection string parsing support

- [ ] Implement MRCServer class
  - [ ] Constructor with Redis config
  - [ ] Context manager support
  - [ ] drop_outdated_cache() with SCAN and regex

### Phase 3: Testing
- [ ] Set up pytest configuration
- [ ] Write test_cache.py
  - [ ] Test cache hit/miss
  - [ ] Test TTL expiration
  - [ ] Test with_cache()
  - [ ] Test drop_outdated_cache()
  - [ ] Mock MySQL for isolated testing
- [ ] Write test_mysql.py (optional integration tests)
- [ ] Verify test coverage >80%

### Phase 4: Documentation
- [ ] Complete Python README.md with examples
- [ ] Add comprehensive docstrings
- [ ] Create global README.md
- [ ] Add usage examples

### Phase 5: Publishing Preparation
- [ ] Verify pyproject.toml metadata
- [ ] Build package: `uv build`
- [ ] Test installation from dist
- [ ] Verify import paths
- [ ] Check type hints with mypy

### Phase 6: Publishing
- **Deployment**: Use Lambda layers or container images with dependencies

## Virtual Environment Management with uv

**Key Points:**
- `uv sync` automatically creates `.venv/` directory in Python/
- No manual activation needed - `uv run` handles it
- Virtual environment is gitignored (add `.venv/` to .gitignore)
- Lock file `uv.lock` ensures reproducible builds
- To manually activate (if needed): `source Python/.venv/bin/activate`
- To deactivate: `deactivate`

**Commands:**
```bash
# Create/sync venv
uv sync

# Run commands in venv (no activation needed)
uv run pytest
uv run python script.py

# Add new dependency
uv add package-name

# Show venv location
uv run python -c "import sys; print(sys.prefix)"
```
- [ ] Build distribution: `make build-py`
- [ ] Test PyPI (testpypi)
- [ ] Publish to PyPI: `make publish-py`
- [ ] Verify installation: `pip install actvalue.mysql-redis-cache`

---

## Key Differences from TypeScript

1. **Async/Await**: Python uses `async`/`await` instead of Promises
2. **Connection Pooling**: aiomysql.create_pool() vs mysql2.createPool()
3. **Type Hints**: Python type annotations vs TypeScript types
4. **Context Managers**: Python `async with` for resource management
5. **Error Handling**: Raise exceptions instead of console.log
6. **Import Style**: `from mysql_redis_cache import` vs `import { } from`
7. **Naming**: snake_case methods vs camelCase

## AWS Lambda Considerations

- **aiomysql**: Compatible with Lambda (pure Python + C extensions)
- **Connection Pooling**: Reuse connections across invocations
- **Context Manager**: Use for proper cleanup
- **Cold Start**: First invocation will be slower (connection setup)
- **Environment Variables**: Store credentials in Lambda env vars

---

## Notes

- TTL jitter prevents cache stampede (all entries expiring simultaneously)
- SHA1 hash ensures query uniqueness regardless of formatting
- SCAN instead of KEYS for production Redis safety
- Context managers ensure proper connection cleanup
- Full type hints enable IDE autocomplete and type checking
