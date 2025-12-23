import { createClient, RedisClientOptions, RedisClientType } from 'redis';

export default class Server {
  redisConfig: RedisClientOptions | undefined;
  redisClient: RedisClientType | undefined;

  /**
   * @param redisConfig - The configuration for Redis.
   */
  constructor(redisConfig: RedisClientOptions) {
    this.redisConfig = redisConfig;
  }

  /**
   * Connect to a Redis instance.
   */
  async _connectRedis() {
    this.redisClient = createClient(this.redisConfig) as RedisClientType;
    this.redisClient.on('error', (err) => {
      this.redisClient = undefined;
      console.log('Redis Client Error', err);
    });
    await this.redisClient.connect();
  }

  /**
   * Disconnect from Redis.
   */
  async closeRedisConnection() {
    await this.redisClient?.quit();
  }

  /**
   * Delete all cached queries where the key matches the given keys.
   * @param keyNames - The names of the modified keys.
   * @param keyValues - The values of the modified keys.
   * @returns The number of deleted records.
   */
  async dropOutdatedCache(
    keyNames: string[],
    keyValues: any[],
  ): Promise<number> {
    // check Redis connection
    if (!this.redisClient) await this._connectRedis();
    if (!this.redisClient) return 0;

    // build regex from key names and values
    let keyRegexString = '';
    for (let i = 0; i < keyNames.length; i++) {
      keyRegexString += '' + keyNames[i] + '=' + keyValues[i] + '|';
    }
    keyRegexString = keyRegexString.slice(0, -1);
    const keyRegex = new RegExp(keyRegexString);

    // loop over all keys and find those who match the regex
    let reply = { cursor: '0', keys: [''] };
    let deletedCount = 0;
    do {
      reply = await this.redisClient.scan(reply.cursor);
      for (const key of reply.keys) {
        // delete key if it matches
        if (keyRegex.test(key)) {
          await this.redisClient.del(key);
          deletedCount++;
        }
      }
    } while (reply.cursor !== '0');

    return deletedCount;
  }
}
