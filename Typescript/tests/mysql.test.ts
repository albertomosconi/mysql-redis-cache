import { MRCClient } from '../src';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { RowDataPacket } from 'mysql2/promise';

const mysqlConfig = {
  host: process.env.MYSQL_HOST || 'localhost',
  port: parseInt(process.env.MYSQL_PORT || '3306'),
  user: process.env.MYSQL_USER || 'test',
  password: process.env.MYSQL_PASSWORD || 'password',
};

const dbName = 'test_mysql_redis_cache';
const tableName = 'test_users';

let client: MRCClient;

beforeAll(async () => {
  // Create client without database to create the database first
  client = new MRCClient(mysqlConfig);
  const pool = client.getMySQLPool();

  // Create database
  await pool?.query(`CREATE DATABASE IF NOT EXISTS ${dbName}`);
  await pool?.query(`USE ${dbName}`);

  // Create table
  await pool?.query(`
    CREATE TABLE IF NOT EXISTS ${tableName} (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(100) NOT NULL,
      email VARCHAR(100) NOT NULL,
      age INT
    )
  `);

  // Seed data
  await pool?.query(`
    INSERT INTO ${tableName} (name, email, age) VALUES
    ('Alice Johnson', 'alice@example.com', 30),
    ('Bob Smith', 'bob@example.com', 25),
    ('Charlie Brown', 'charlie@example.com', 35)
  `);
});

describe('MySQL Connection Tests', () => {
  it('should connect to MySQL and get pool', () => {
    const pool = client.getMySQLPool();
    expect(pool).toBeDefined();
  });

  it('should connect using connection string', async () => {
    const connectionString = `mysql://${mysqlConfig.user}:${mysqlConfig.password}@${mysqlConfig.host}:${mysqlConfig.port}/${dbName}`;
    const stringClient = new MRCClient(connectionString);
    const pool = stringClient.getMySQLPool();
    
    expect(pool).toBeDefined();
    
    // Test a simple query
    const result = await stringClient.queryToPromise(`SELECT * FROM ${tableName}`);
    expect(result).toBeDefined();
    expect(Array.isArray(result)).toBe(true);
    
    await pool?.end();
  });

  it('should execute a simple SELECT query', async () => {
    const result = await client.queryToPromise(`SELECT * FROM ${tableName}`);
    expect(result).toBeDefined();
    expect(Array.isArray(result)).toBe(true);
    expect(result.length).toBe(3);
  });

  it('should execute a parameterized query', async () => {
    const result = await client.queryToPromise(
      `SELECT * FROM ${tableName} WHERE id = ?`,
      [1]
    ) as RowDataPacket[];
    
    expect(result).toBeDefined();
    expect(result.length).toBe(1);
    expect(result[0].name).toBe('Alice Johnson');
    expect(result[0].email).toBe('alice@example.com');
  });

  it('should execute a query with multiple parameters', async () => {
    const result = await client.queryToPromise(
      `SELECT * FROM ${tableName} WHERE age > ? AND age < ?`,
      [20, 40]
    );
    
    expect(result).toBeDefined();
    expect(result.length).toBe(3);
  });

  it('should handle INSERT queries', async () => {
    const insertResult: any = await client.queryToPromise(
      `INSERT INTO ${tableName} (name, email, age) VALUES (?, ?, ?)`,
      ['David Wilson', 'david@example.com', 28]
    );
    
    expect(insertResult.affectedRows).toBe(1);
    expect(insertResult.insertId).toBeGreaterThan(0);

    // Verify the insert
    const selectResult = await client.queryToPromise(
      `SELECT * FROM ${tableName} WHERE id = ?`,
      [insertResult.insertId]
    ) as RowDataPacket[];
    
    expect(selectResult[0].name).toBe('David Wilson');
  });

  it('should handle UPDATE queries', async () => {
    const updateResult: any = await client.queryToPromise(
      `UPDATE ${tableName} SET age = ? WHERE name = ?`,
      [31, 'Alice Johnson']
    );
    
    expect(updateResult.affectedRows).toBe(1);

    // Verify the update
    const selectResult = await client.queryToPromise(
      `SELECT age FROM ${tableName} WHERE name = ?`,
      ['Alice Johnson']
    ) as RowDataPacket[];
    
    expect(selectResult[0].age).toBe(31);
  });

  it('should handle DELETE queries', async () => {
    const deleteResult: any = await client.queryToPromise(
      `DELETE FROM ${tableName} WHERE name = ?`,
      ['Charlie Brown']
    );
    
    expect(deleteResult.affectedRows).toBe(1);

    // Verify the delete
    const selectResult = await client.queryToPromise(
      `SELECT * FROM ${tableName} WHERE name = ?`,
      ['Charlie Brown']
    );
    
    expect(selectResult.length).toBe(0);
  });
});

afterAll(async () => {
  const pool = client.getMySQLPool();
  
  // Drop table and database
  await pool?.query(`DROP TABLE IF EXISTS ${tableName}`);
  await pool?.query(`DROP DATABASE IF EXISTS ${dbName}`);
  
  // Close pool
  await pool?.end();
});
