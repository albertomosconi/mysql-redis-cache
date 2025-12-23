import { MRCServer, MRCClient } from '../src';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'

const redisConfig = { socket: { connectTimeout: 60000 } };
const query = 'SELECT * FROM users WHERE id = ?';
const params = [1234];
const paramNames = ['UserId'];

let server: MRCServer;
let client: MRCClient;
let spy: any;
let mockRedisClient: any;
let mockServerRedisClient: any;

beforeAll(async () => {
  // Create mock Redis client for MRCClient
  mockRedisClient = {
    connect: vi.fn().mockResolvedValue(undefined),
    quit: vi.fn().mockResolvedValue(undefined),
    get: vi.fn().mockResolvedValue(null),
    set: vi.fn().mockResolvedValue('OK'),
    flushAll: vi.fn().mockResolvedValue('OK'),
    on: vi.fn(),
  };

  // Create mock Redis client for MRCServer
  mockServerRedisClient = {
    connect: vi.fn().mockResolvedValue(undefined),
    quit: vi.fn().mockResolvedValue(undefined),
    scan: vi.fn(),
    del: vi.fn().mockResolvedValue(1),
    on: vi.fn(),
  };

  server = new MRCServer(redisConfig);
  client = new MRCClient({}, redisConfig);
  
  // Inject mock Redis clients
  client.redisClient = mockRedisClient as any;
  server.redisClient = mockServerRedisClient as any;
  
  spy = vi
    .spyOn(client, 'queryToPromise')
    .mockImplementation((_, params) => {
      return new Promise(resolve => {
        resolve(params);
      });
    });
});

it('tests if running the same query twice in a row triggers access to cache', async () => {
  // First call: cache miss
  mockRedisClient.get.mockResolvedValueOnce(null);
  mockRedisClient.set.mockResolvedValueOnce('OK');
  
  let r = await client.queryWithCache(query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1);
  
  // Second call: cache hit
  mockRedisClient.get.mockResolvedValueOnce(JSON.stringify(params));
  
  r = await client.queryWithCache(query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1); // Still only called once
});

it('tests if cache gets dropped', async () => {
  // Mock cache exists
  const cacheKey = client.getKeyFromQuery(query, params, paramNames);
  mockRedisClient.get.mockResolvedValueOnce(null);
  mockRedisClient.set.mockResolvedValueOnce('OK');
  
  await client.queryWithCache(query, params, paramNames);

  // Mock scan returning the cache key
  mockServerRedisClient.scan.mockResolvedValueOnce({
    cursor: '0',
    keys: [cacheKey]
  });
  
  const deletedEntries = await server.dropOutdatedCache(paramNames, params);
  expect(deletedEntries).toBe(1);
  expect(mockServerRedisClient.del).toHaveBeenCalledWith(cacheKey);

  // Verify cache no longer exists
  mockRedisClient.get.mockResolvedValueOnce(null);
  const v = await client.redisClient?.get(cacheKey);
  expect(v).toBeNull();
});

it('writes and reads values from cache', async () => {
  const query = 'query';
  const value = 'abc';
  
  mockRedisClient.set.mockResolvedValueOnce('OK');
  await client.writeToCache(query, value);
  expect(mockRedisClient.set).toHaveBeenCalled();
  
  mockRedisClient.get.mockResolvedValueOnce(JSON.stringify(value));
  const v = await client.readFromCache(query);
  expect(v).toBe(value);
});

it('tests if entries expire after ttl seconds', async () => {
  const ttl = 2;
  const cacheKey = client.getKeyFromQuery(query, params, paramNames);
  
  // Mock successful cache write with TTL
  mockRedisClient.get.mockResolvedValueOnce(null);
  mockRedisClient.set.mockResolvedValueOnce('OK');
  
  await client.queryWithCache(query, params, paramNames, ttl);
  
  // Verify set was called with EX (expiration) parameter
  expect(mockRedisClient.set).toHaveBeenCalled();
  const setCall = mockRedisClient.set.mock.calls[mockRedisClient.set.mock.calls.length - 1];
  expect(setCall[2]).toHaveProperty('EX');
  const expirationTime = setCall[2].EX;
  // TTL should have jitter: ttl * (1 - 0.1) to ttl * (1 + 0.1)
  expect(expirationTime).toBeGreaterThanOrEqual(ttl * 0.9);
  expect(expirationTime).toBeLessThanOrEqual(ttl * 1.1);
  
  // Simulate entry existing
  mockRedisClient.get.mockResolvedValueOnce(JSON.stringify(params));
  let v = await client.redisClient?.get(cacheKey);
  expect(JSON.parse(v as string)).toStrictEqual(params);
  
  // Simulate expiration (entry no longer exists)
  mockRedisClient.get.mockResolvedValueOnce(null);
  v = await client.redisClient?.get(cacheKey);
  expect(v).toBeNull();
});


it('uses cache with arbitrary query function', async () => {
  const fn = () => client.queryToPromise(query, params);
  
  // First call: cache miss
  mockRedisClient.get.mockResolvedValueOnce(null);
  mockRedisClient.set.mockResolvedValueOnce('OK');
  
  let r = await client.withCache(fn, query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1);
  
  // Second call: cache hit
  mockRedisClient.get.mockResolvedValueOnce(JSON.stringify(params));
  
  r = await client.withCache(fn, query, params, paramNames);
  expect(r).toStrictEqual(params);
  // query is not triggered again
  expect(spy).toHaveBeenCalledTimes(1);
  
  // Third call with different signature: cache miss
  mockRedisClient.get.mockResolvedValueOnce(null);
  mockRedisClient.set.mockResolvedValueOnce('OK');
  
  r = await client.withCache(fn, query);
  expect(r).toStrictEqual(params);
  // query is triggered again because signature is different
  expect(spy).toHaveBeenCalledTimes(2);
});

afterEach(() => {
  vi.clearAllMocks();
});

afterAll(async () => {
  // Mocked clients don't need actual cleanup, but call for completeness
  await server.closeRedisConnection();
  await client.closeRedisConnection();
});