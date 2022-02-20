import crypto from 'crypto';
import { createPool, Pool, PoolConfig } from 'mysql';
import { createClient, RedisClientOptions, RedisClientType } from 'redis';

class MRCInstance {
  mysqlPool: Pool;
  redisClient: RedisClientType | undefined;

  constructor(mysqlConfig: PoolConfig) {
    this.mysqlPool = createPool(mysqlConfig);
  }

  /**
   * Connect to a Redis instance.
   * @param config - The Redis config.
   */
  async connectRedis(config?: RedisClientOptions) {
    this.redisClient = createClient(config) as RedisClientType;
    this.redisClient.on('error', (err) =>
      console.log('Redis Client Error', err),
    );
    await this.redisClient.connect();
  }

  /**
   * Execute the given query as Promise
   * @param query - A MySQL query.
   * @param params - An array of parameters for the query.
   * @returns - The result of the query.
   */
  queryToPromise(query: string, params?: any[]): Promise<any> {
    return new Promise((resolve, reject) => {
      return this.mysqlPool.query(query, params, (error, rows) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(rows);
      });
    });
  }

  /**
   * Generate a unique key from the given query and parameters.
   * @param query - A MySQL query.
   * @param params - The parameters for the query.
   * @param paramNames - The names of the query parameters.
   * @returns - The key corresponding to the given query and parameters.
   */
  getKeyFromQuery(
    query: string,
    params?: any[],
    paramNames: string[] = [],
  ): string {
    const hash = crypto.createHash('sha1').update(query).digest('hex');
    let key = '';
    if (params && params.length > 0)
      paramNames.forEach((name, i) => {
        key += name + '=' + params[i] + '_';
      });
    key += hash;
    return key;
  }

  /**
   * Check the cache before executing a MySQL query.
   * @param query - A MySQL query.
   * @param params - The parameters for the query.
   * @param paramNames - The names of the query parameters.
   * @param ttl - Expiration time in seconds for the query cache.
   * @returns - The query result.
   */
  async queryWithCache(
    query: string,
    params?: any[],
    paramNames: string[] = [],
    ttl = 86400,
  ) {
    const key = this.getKeyFromQuery(query, params, paramNames);
    // get cached query result from redis
    const result = await this.redisClient?.get(key);
    // if found return cached value
    if (result) return JSON.parse(result);
    // else execute query
    const r = await this.queryToPromise(query, params);
    // set key with ttl
    const dt = Math.round(ttl * (Math.random() * 0.2 - 0.1));
    await this.redisClient?.set(key, JSON.stringify(r), {
      EX: ttl + dt,
    });
    // return query result
    return r;
  }
}

module.exports = {
  MRCInstance,
};
