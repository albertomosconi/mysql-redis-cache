import { MRCServer, MRCClient } from '../src';

const redisConfig = { socket: { connectTimeout: 60000 } };
const query = 'SELECT * FROM users WHERE id = ?';
const params = [1234];
const paramNames = ['UserId'];

let server: MRCServer;
let client: MRCClient;
let spy: jest.SpyInstance;

beforeAll(async () => {
  server = new MRCServer(redisConfig);
  client = new MRCClient({}, redisConfig);
  await client._connectRedis();
  await client.redisClient?.flushAll();
  spy = jest
    .spyOn(client, 'queryToPromise')
    .mockImplementation((_, params) => {
      return new Promise(resolve => {
        resolve(params);
      });
    });
});

it('tests if running the same query twice in a row triggers access to cache', async () => {
  let r = await client.queryWithCache(query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1);
  // calling again doesn't trigger queryToPromise
  r = await client.queryWithCache(query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1);
});

it('tests if cache gets dropped', async () => {
  await client.queryWithCache(query, params, paramNames);

  const deletedEntries = await server.dropOutdatedCache(paramNames, params);
  expect(deletedEntries).toBe(1);

  const v = await client.redisClient?.get(
    client.getKeyFromQuery(query, params, paramNames),
  );
  expect(v).toBeNull();
});

it('tests if entries expire after ttl seconds', async () => {
  const ttl = 2;
  await client.queryWithCache(query, params, paramNames, ttl);
  let v = await client.redisClient?.get(
    client.getKeyFromQuery(query, params, paramNames),
  );
  expect(JSON.parse(v as string)).toStrictEqual(params);
  await new Promise((r) => setTimeout(r, ttl * 1000));
  v = await client.redisClient?.get(
    client.getKeyFromQuery(query, params, paramNames),
  );
  expect(v).toBeNull();
});

it('writes and reads values from cache', async () => {
  const query = 'query';
  const value = 'abc';
  await client.writeToCache(query, value);
  const v = await client.readFromCache(query);
  expect(v).toBe(value);
});

it('uses cache with arbitrary query function', async () => {
  const fn = () => client.queryToPromise(query, params);
  let r = await client.withCache(fn, query, params, paramNames);
  expect(r).toStrictEqual(params);
  expect(spy).toHaveBeenCalledTimes(1);
  r = await client.withCache(fn, query, params, paramNames);
  expect(r).toStrictEqual(params);
  // query is not triggered again
  expect(spy).toHaveBeenCalledTimes(1);
  r = await client.withCache(fn, query);
  expect(r).toStrictEqual(params);
  // query is triggered again bcause signature is different
  expect(spy).toHaveBeenCalledTimes(2);
});

afterEach(() => {
  jest.clearAllMocks();
});

afterAll(async () => {
  await server.closeRedisConnection();
  await client.closeRedisConnection();
});
