# @actvalue/mysql-redis-cache

wrapper for MySQL queries with Redis caching

## Install

```bash
yarn add @actvalue/mysql-redis-cache
```

```bash
npm i @actvalue/mysql-redis-cache
```

## Usage

```javascript
import { MRCInstance } from '@actvalue/mysql-redis-cache';

const mysqlConfig = {
  host: '<mysql host>',
  port: 3306,
  user: '<user>',
  password: '<password>',
  database: '<db>',
  connectionLimit: 5,
};

const redisConfig = {
  username: '<user>',
  password: '<password>',
  socket: {
    host: '<redis host>',
    port: 6379,
    connectionTimeout: 30000,
  },
};

// create instance and connect
const mrc = new MRCInstance(mysqlConfig);
await mrc.connectRedis(redisConfig);

// execute queries
const query = 'SELECT * FROM table WHERE name = ?';
const params = ['Alberto'];
const paramNames = ['Name'];
const ttl = 3600;

const result = await mrc.queryWithCache(query, params, paramNames, ttl);
```
