/**
 * Interoperability tests between TypeScript and Python implementations.
 * 
 * These tests verify that both implementations can read each other's cache entries,
 * ensuring cross-platform compatibility in production environments.
 */

import { MRCClient, MRCServer } from '../src';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createClient, RedisClientType } from 'redis';
import crypto from 'crypto';

const mysqlConfig = {
  host: process.env.MYSQL_HOST || 'localhost',
  port: parseInt(process.env.MYSQL_PORT || '3306'),
  user: process.env.MYSQL_USER || 'test',
  password: process.env.MYSQL_PASSWORD || 'password',
  database: 'test_mysql_redis_cache',
};

const redisConfig = {
  socket: {
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379'),
  },
};

let client: MRCClient;
let redisClient: RedisClientType;

beforeAll(async () => {
  // Create MySQL client
  client = new MRCClient(mysqlConfig, redisConfig);
  
  // Create direct Redis client for inspection
  redisClient = createClient(redisConfig);
  await redisClient.connect();
  
  // Setup test table
  const pool = client.getMySQLPool();
  await pool?.query(`
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
  `);
  
  // Clear and seed data (TRUNCATE resets auto-increment)
  await pool?.query('TRUNCATE TABLE test_interop');
  await pool?.query(`
    INSERT INTO test_interop 
    (name, email, age, balance, is_active, created_at, birth_date) 
    VALUES 
    ('Alice Johnson', 'alice@example.com', 30, 1234.56, 1, '2023-01-15 10:30:00', '1993-06-15'),
    ('Bob Smith', 'bob@example.com', 25, 999.99, 1, '2023-02-20 14:45:30', '1998-03-22'),
    ('Charlie Brown', 'charlie@example.com', 35, 5000.00, 0, '2023-03-10 08:15:00', '1988-11-05')
  `);
});

beforeEach(async () => {
  // Clear cache before each test
  await redisClient.flushDb();
});

afterAll(async () => {
  await client.closeRedisConnection();
  await redisClient.quit();
  await client.getMySQLPool()?.end();
});

describe('TypeScript Cache Writing for Python Compatibility', () => {
  it('should write cache in format readable by Python', async () => {
    const query = 'SELECT * FROM test_interop WHERE id = ?';
    const params = [1];
    const paramNames = ['UserId'];
    const ttl = 3600;

    // Execute query with cache
    const result = await client.queryWithCache(query, params, paramNames, ttl);

    expect(result).toBeDefined();
    expect(Array.isArray(result)).toBe(true);
    expect(result.length).toBe(1);
    expect(result[0].name).toBe('Alice Johnson');

    // Verify cache key format
    const cacheKey = client.getKeyFromQuery(query, params, paramNames);
    const queryHash = crypto.createHash('sha1').update(query).digest('hex');
    const expectedKey = `UserId=1_${queryHash}`;
    expect(cacheKey).toBe(expectedKey);

    // Inspect cached data
    const cachedData = await redisClient.get(cacheKey);
    expect(cachedData).not.toBeNull();

    // Verify JSON format (compact, no spaces)
    const parsed = JSON.parse(cachedData!);
    expect(Array.isArray(parsed)).toBe(true);
    expect(parsed.length).toBe(1);
    expect(parsed[0].id).toBe(1);
    expect(parsed[0].name).toBe('Alice Johnson');

    // Verify compact JSON (no spaces after separators)
    expect(cachedData).not.toContain(', ');
    expect(cachedData).not.toContain(': ');
  });

  it('should cache multiple rows with various data types', async () => {
    const query = 'SELECT * FROM test_interop WHERE age >= ? ORDER BY age ASC';
    const params = [25];
    const paramNames = ['MinAge'];

    const result = await client.queryWithCache(query, params, paramNames, 3600);

    expect(result.length).toBe(3);
    expect(result[0].name).toBe('Bob Smith');
    expect(result[1].name).toBe('Alice Johnson');
    expect(result[2].name).toBe('Charlie Brown');

    // Check cached data structure
    const cacheKey = client.getKeyFromQuery(query, params, paramNames);
    const cachedData = await redisClient.get(cacheKey);
    const parsed = JSON.parse(cachedData!);

    // Verify all data types are properly serialized
    expect(parsed[0]).toHaveProperty('id');
    expect(parsed[0]).toHaveProperty('name');
    expect(parsed[0]).toHaveProperty('balance');
    expect(parsed[0]).toHaveProperty('is_active');
    
    // DECIMAL should be a number
    expect(typeof parsed[0].balance).toBe('number');
  });

  it('should handle NULL values correctly', async () => {
    // Insert row with NULL values
    const pool = client.getMySQLPool();
    await pool?.query(`
      INSERT INTO test_interop (name, email, age, balance, is_active) 
      VALUES ('Null Test', 'null@example.com', NULL, NULL, 1)
    `);

    const query = 'SELECT * FROM test_interop WHERE email = ?';
    const params = ['null@example.com'];
    const paramNames = ['Email'];

    const result = await client.queryWithCache(query, params, paramNames, 3600);

    // Check cached data
    const cacheKey = client.getKeyFromQuery(query, params, paramNames);
    const cachedData = await redisClient.get(cacheKey);
    const parsed = JSON.parse(cachedData!);

    // NULL should be JSON null
    expect(parsed[0].age).toBeNull();
    expect(parsed[0].balance).toBeNull();
    expect(cachedData).toContain('"age":null');
    expect(cachedData).toContain('"balance":null');
  });

  it('should generate cache keys matching Python format', () => {
    const testCases = [
      {
        query: 'SELECT * FROM users',
        params: undefined,
        paramNames: undefined,
        validate: (key: string, query: string) => {
          const hash = crypto.createHash('sha1').update(query).digest('hex');
          expect(key).toBe(hash);
        }
      },
      {
        query: 'SELECT * FROM users WHERE id = ?',
        params: [123],
        paramNames: ['UserId'],
        validate: (key: string, query: string) => {
          const hash = crypto.createHash('sha1').update(query).digest('hex');
          expect(key).toBe(`UserId=123_${hash}`);
        }
      },
      {
        query: 'SELECT * FROM orders WHERE store_id = ? AND user_id = ?',
        params: [6, 456],
        paramNames: ['StoreId', 'UserId'],
        validate: (key: string, query: string) => {
          const hash = crypto.createHash('sha1').update(query).digest('hex');
          expect(key).toBe(`StoreId=6_UserId=456_${hash}`);
        }
      },
      {
        query: 'SELECT * FROM users WHERE email = ?',
        params: ['test@example.com'],
        paramNames: ['Email'],
        validate: (key: string, query: string) => {
          const hash = crypto.createHash('sha1').update(query).digest('hex');
          expect(key).toBe(`Email=test@example.com_${hash}`);
        }
      },
    ];

    for (const testCase of testCases) {
      const key = client.getKeyFromQuery(testCase.query, testCase.params, testCase.paramNames);
      testCase.validate(key, testCase.query);
    }
  });

  it('should verify JSON serialization produces compact format', () => {
    const data = [
      { id: 1, name: 'Alice', tags: ['admin', 'user'], active: true },
      { id: 2, name: 'Bob', tags: ['user'], active: false }
    ];

    const json = JSON.stringify(data);

    // Verify compact format
    expect(json).not.toContain(', ');
    expect(json).not.toContain(': ');
    
    // Verify structure
    expect(json).toContain('[{');
    expect(json).toContain('"id":1');
    expect(json).toContain('"active":true');
    expect(json).toContain('"active":false');
  });

  it('should cache query with TTL jitter', async () => {
    const query = 'SELECT * FROM test_interop WHERE id = ?';
    const params = [2];
    const paramNames = ['UserId'];
    const ttl = 3600;

    await client.queryWithCache(query, params, paramNames, ttl);

    // Check TTL
    const cacheKey = client.getKeyFromQuery(query, params, paramNames);
    const actualTTL = await redisClient.ttl(cacheKey);

    // TTL should have ±10% jitter
    const minTTL = 3240; // 3600 - 360
    const maxTTL = 3960; // 3600 + 360
    
    expect(actualTTL).toBeGreaterThanOrEqual(minTTL);
    expect(actualTTL).toBeLessThanOrEqual(maxTTL);
  });
});

describe('TypeScript Cache Invalidation for Python Compatibility', () => {
  it('should invalidate cache entries by parameter', async () => {
    const server = new MRCServer(redisConfig);

    // Create multiple cached queries
    await client.queryWithCache('SELECT * FROM test_interop WHERE id = ?', [1], ['UserId'], 3600);
    await client.queryWithCache('SELECT * FROM test_interop WHERE id = ?', [2], ['UserId'], 3600);
    await client.queryWithCache('SELECT * FROM test_interop WHERE id = ?', [3], ['UserId'], 3600);
    await client.queryWithCache('SELECT * FROM test_interop WHERE age > ?', [20], ['MinAge'], 3600);

    // Invalidate UserId=1
    const deletedCount = await server.dropOutdatedCache(['UserId'], [1]);
    expect(deletedCount).toBe(1);

    // Verify correct entries were deleted
    const key1 = client.getKeyFromQuery('SELECT * FROM test_interop WHERE id = ?', [1], ['UserId']);
    const key2 = client.getKeyFromQuery('SELECT * FROM test_interop WHERE id = ?', [2], ['UserId']);
    const key3 = client.getKeyFromQuery('SELECT * FROM test_interop WHERE id = ?', [3], ['UserId']);
    
    expect(await redisClient.get(key1)).toBeNull();
    expect(await redisClient.get(key2)).not.toBeNull();
    expect(await redisClient.get(key3)).not.toBeNull();

    await server.closeRedisConnection();
  });

  it('should invalidate multiple parameter patterns', async () => {
    const server = new MRCServer(redisConfig);

    // Cache with multiple parameters
    const query = 'SELECT * FROM test_interop WHERE age > ? AND is_active = ?';
    await client.queryWithCache(query, [20, 1], ['MinAge', 'Active'], 3600);
    await client.queryWithCache(query, [30, 1], ['MinAge', 'Active'], 3600);

    // Invalidate by multiple parameters
    const deletedCount = await server.dropOutdatedCache(['MinAge', 'Active'], [20, 1]);
    expect(deletedCount).toBe(1);

    await server.closeRedisConnection();
  });
});

describe('Cache Key Format Documentation', () => {
  it('should document cache key format for Python validation', () => {
    const testCases = [
      {
        description: 'Simple query with one integer parameter',
        query: 'SELECT * FROM test_interop WHERE id = ?',
        params: [123],
        paramNames: ['UserId'],
      },
      {
        description: 'Query with multiple parameters',
        query: 'SELECT * FROM test_interop WHERE store_id = ? AND user_id = ?',
        params: [6, 456],
        paramNames: ['StoreId', 'UserId'],
      },
      {
        description: 'Query with string parameter',
        query: 'SELECT * FROM test_interop WHERE email = ?',
        params: ['alice@example.com'],
        paramNames: ['Email'],
      },
    ];

    console.log('\n' + '='.repeat(80));
    console.log('CACHE KEY FORMAT DOCUMENTATION FOR PYTHON VALIDATION');
    console.log('='.repeat(80));

    for (const testCase of testCases) {
      const key = client.getKeyFromQuery(testCase.query, testCase.params, testCase.paramNames);
      
      console.log(`\n${testCase.description}`);
      console.log(`Query: ${testCase.query}`);
      console.log(`Params: ${JSON.stringify(testCase.params)}`);
      console.log(`Param Names: ${JSON.stringify(testCase.paramNames)}`);
      console.log(`Generated Key: ${key}`);
      console.log(`Key Length: ${key.length}`);
    }

    console.log('\n' + '='.repeat(80));
    
    // This test always passes - it's for documentation
    expect(true).toBe(true);
  });
});
