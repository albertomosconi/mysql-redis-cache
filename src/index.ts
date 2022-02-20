import { createPool, PoolConfig, Pool } from 'mysql';

class MRCInstance {
  mysqlPool: Pool;

  constructor(mysqlConfig: PoolConfig) {
    this.mysqlPool = createPool(mysqlConfig);
  }

  /**
   * Execute the given query as Promise
   * @param query - A MySQL query.
   * @param params - An array of parameters for the query.
   * @returns - The result of the query.
   */
  queryToPromise(query: string, params: any[]): Promise<any> {
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
}

module.exports = {
  MRCInstance,
};
